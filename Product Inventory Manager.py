import tkinter as tk
from tkinter import ttk, messagebox
import pyodbc
from datetime import datetime
import os
import subprocess

# ---------------- SQL SERVER CONNECTION ----------------
SERVER = r"DESKTOP-M6805A7\SQLEXPRESS" 
 # Update to your server
DATABASE = "billing"

def connect():
    return pyodbc.connect(
        f"DRIVER={{ODBC Driver 17 for SQL Server}};"
        f"SERVER={SERVER};DATABASE={DATABASE};Trusted_Connection=yes;Encrypt=no;"
    )

# ---------------- ENSURE TABLES ----------------
def ensure_tables():
    try:
        conn = connect()
        cur = conn.cursor()
        # Products table
        cur.execute("""
        IF OBJECT_ID('dbo.products', 'U') IS NULL
        BEGIN
            CREATE TABLE dbo.products (
                id INT IDENTITY(1,1) PRIMARY KEY,
                name VARCHAR(255) NOT NULL UNIQUE,
                price FLOAT NOT NULL DEFAULT 0,
                stock INT NOT NULL DEFAULT 0
            );
        END
        """)
        # Billing records table
        cur.execute("""
        IF OBJECT_ID('dbo.billing_records', 'U') IS NULL
        BEGIN
            CREATE TABLE dbo.billing_records (
                id INT IDENTITY(1,1) PRIMARY KEY,
                customer_name VARCHAR(100),
                product_id INT,
                product_name VARCHAR(255),
                quantity INT,
                total FLOAT,
                created_at DATETIME DEFAULT GETDATE()
            );
        END
        """)
        conn.commit()
        conn.close()
    except Exception as e:
        messagebox.showerror("DB Error", str(e))

# ---------------- GLOBAL VARIABLES ----------------
LOW_STOCK_THRESHOLD = 5
RECEIPT_DIR = "receipts"
if not os.path.exists(RECEIPT_DIR):
    os.makedirs(RECEIPT_DIR)

# ---------------- FETCH PRODUCTS ----------------
def fetch_products():
    for row in table.get_children():
        table.delete(row)
    try:
        conn = connect()
        cur = conn.cursor()
        cur.execute("SELECT id, name, price, stock FROM products ORDER BY id")
        rows = cur.fetchall()
        conn.close()
        for r in rows:
            pid, pname, pprice, pstock = r
            pprice = float(pprice) if pprice else 0
            pstock = int(pstock) if pstock else 0
            item_id = table.insert("", tk.END, values=(pid, pname, f"{pprice:.2f}", pstock))
            if pstock <= LOW_STOCK_THRESHOLD:
                table.item(item_id, tags=("low",))
    except Exception as e:
        messagebox.showerror("Error", str(e))

# ---------------- CRUD ----------------
def add_product():
    name = name_var.get().strip()
    price_text = price_var.get().strip()
    stock_text = stock_var.get().strip()
    if not name or not price_text or not stock_text:
        messagebox.showerror("Error", "All fields required!")
        return
    try:
        price_value = float(price_text)
        stock_value = int(stock_text)
        conn = connect()
        cur = conn.cursor()
        cur.execute("INSERT INTO products (name, price, stock) VALUES (?, ?, ?)",
                    (name, price_value, stock_value))
        conn.commit()
        conn.close()
        name_var.set("")
        price_var.set("")
        stock_var.set("")
        fetch_products()
    except Exception as e:
        messagebox.showerror("Error", str(e))

def update_product():
    selected = table.focus()
    if not selected:
        messagebox.showwarning("Warning", "Select a product to update")
        return
    pid = table.item(selected, "values")[0]
    name = name_var.get().strip()
    price_text = price_var.get().strip()
    stock_text = stock_var.get().strip()
    if not name or not price_text or not stock_text:
        messagebox.showerror("Error", "All fields required!")
        return
    try:
        price_value = float(price_text)
        stock_value = int(stock_text)
        conn = connect()
        cur = conn.cursor()
        cur.execute("UPDATE products SET name=?, price=?, stock=? WHERE id=?",
                    (name, price_value, stock_value, pid))
        conn.commit()
        conn.close()
        name_var.set("")
        price_var.set("")
        stock_var.set("")
        fetch_products()
    except Exception as e:
        messagebox.showerror("Error", str(e))

def delete_product():
    selected = table.focus()
    if not selected:
        messagebox.showwarning("Warning", "Select a product to delete")
        return
    pid = table.item(selected, "values")[0]
    confirm = messagebox.askyesno("Confirm", "Are you sure you want to delete this product?")
    if not confirm:
        return
    try:
        conn = connect()
        cur = conn.cursor()
        cur.execute("DELETE FROM products WHERE id=?", (pid,))
        conn.commit()
        conn.close()
        fetch_products()
    except Exception as e:
        messagebox.showerror("Error", str(e))

def select_row(event):
    selected = table.focus()
    if not selected:
        return
    values = table.item(selected, "values")
    name_var.set(values[1])
    price_var.set(values[2])
    stock_var.set(values[3])

# ---------------- SEARCH ----------------
def search_product(keyword):
    keyword = keyword.strip()
    for row in table.get_children():
        table.delete(row)
    try:
        conn = connect()
        cur = conn.cursor()
        cur.execute("""
            SELECT id, name, price, stock FROM products 
            WHERE name LIKE ? OR CAST(id AS VARCHAR(50)) LIKE ? 
            ORDER BY id
        """, (f"%{keyword}%", f"%{keyword}%"))
        rows = cur.fetchall()
        conn.close()
        for r in rows:
            pid, pname, pprice, pstock = r
            pprice = float(pprice) if pprice else 0
            pstock = int(pstock) if pstock else 0
            item_id = table.insert("", tk.END, values=(pid, pname, f"{pprice:.2f}", pstock))
            if pstock <= LOW_STOCK_THRESHOLD:
                table.item(item_id, tags=("low",))
    except Exception as e:
        messagebox.showerror("Error", str(e))
        

# ---------------- GENERATE BILL ----------------
def generate_bill():
    selected = table.focus()
    if not selected:
        messagebox.showwarning("Warning", "Select a product first!")
        return
    values = table.item(selected, "values")
    if not values or len(values) < 4:
        messagebox.showerror("Error", "Selected row data invalid")
        return
    try:
        product_id = int(values[0])
        product_name = str(values[1])
        price = float(values[2])
        stock_available = int(values[3])
    except Exception:
        messagebox.showerror("Error", "Invalid product data")
        return
    customer = customer_var.get().strip()
    if not customer:
        messagebox.showerror("Error", "Customer name required")
        return

    qty = 1  # Always 1 unit for simplicity
    if stock_available < qty:
        messagebox.showerror("Error", f"Not enough stock. Available: {stock_available}")
        return
    total = qty * price

    try:
        conn = connect()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO billing_records (customer_name, product_id, product_name, quantity, total)
            VALUES (?, ?, ?, ?, ?)
        """, (customer, product_id, product_name, qty, total))
        cur.execute("UPDATE products SET stock = stock - ? WHERE id = ?", (qty, product_id))
        conn.commit()
        conn.close()
        customer_var.set("")
        fetch_products()

        # Save receipt
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = os.path.join(RECEIPT_DIR, f"receipt_{timestamp}.txt")
        with open(filename, "w") as f:
            f.write("=== PRODUCT RECEIPT ===\n")
            f.write(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Customer: {customer}\n")
            f.write(f"Product: {product_name}\n")
            f.write(f"Quantity: {qty}\n")
            f.write(f"Price per unit: {price:.2f}\n")
            f.write(f"Total: {total:.2f}\n")
            f.write("=======================\n")

        # Open the receipt automatically
        try:
            if os.name == 'nt':  # Windows
                os.startfile(filename)
            else:  # Mac/Linux
                subprocess.call(['open', filename])  # Mac
                # subprocess.call(['xdg-open', filename])  # Linux
        except Exception as e:
            messagebox.showinfo("Bill Saved", f"Bill saved at {filename}\nCould not open automatically: {e}")

    except Exception as e:
        messagebox.showerror("Error", str(e))

# ---------------- GUI ----------------
root = tk.Tk()
root.title("Inventory & Billing Manager")
root.geometry("850x600")
root.configure(bg="#f5f6fa")

ensure_tables()

# Title
tk.Label(root, text="📦 Product Inventory Manager", font=("Helvetica", 24, "bold"), bg="#f5f6fa").pack(pady=12)

# Input Frame
frame_input = tk.Frame(root, bg="#f5f6fa", bd=2, relief="groove")
frame_input.pack(padx=20, pady=10, fill="x")

name_var = tk.StringVar()
price_var = tk.StringVar()
stock_var = tk.StringVar()

tk.Label(frame_input, text="Product Name:", font=("Arial", 12, "bold"), bg="#f5f6fa").grid(row=0, column=0, padx=10, pady=6, sticky="w")
tk.Entry(frame_input, textvariable=name_var, font=("Arial", 12), width=30).grid(row=0, column=1, padx=10, pady=6)
tk.Label(frame_input, text="Price:", font=("Arial", 12, "bold"), bg="#f5f6fa").grid(row=0, column=2, padx=10, pady=6, sticky="w")
tk.Entry(frame_input, textvariable=price_var, font=("Arial", 12), width=18).grid(row=0, column=3, padx=10, pady=6)
tk.Label(frame_input, text="Stock:", font=("Arial", 12, "bold"), bg="#f5f6fa").grid(row=0, column=4, padx=10, pady=6, sticky="w")
tk.Entry(frame_input, textvariable=stock_var, font=("Arial", 12), width=10).grid(row=0, column=5, padx=10, pady=6)

# Billing Frame
billing_frame = tk.Frame(root, bg="#f5f6fa", bd=2, relief="groove")
billing_frame.pack(padx=20, pady=6, fill="x")

customer_var = tk.StringVar()
tk.Label(billing_frame, text="Customer Name:", font=("Arial", 12, "bold"), bg="#f5f6fa").grid(row=0, column=0, padx=8, pady=6, sticky="w")
tk.Entry(billing_frame, textvariable=customer_var, font=("Arial", 12), width=30).grid(row=0, column=1, padx=8, pady=6)
tk.Button(billing_frame, text="Generate Bill", command=generate_bill, bg="#8e44ad", fg="white", font=("Arial", 12, "bold")).grid(row=0, column=2, padx=10)

# Buttons Frame
frame_buttons = tk.Frame(root, bg="#f5f6fa")
frame_buttons.pack(pady=6)
tk.Button(frame_buttons, text="Add Product", command=add_product, width=14, bg="#2ecc71", fg="white", font=("Arial", 12, "bold")).grid(row=0, column=0, padx=6)
tk.Button(frame_buttons, text="Update Product", command=update_product, width=14, bg="#3498db", fg="white", font=("Arial", 12, "bold")).grid(row=0, column=1, padx=6)
tk.Button(frame_buttons, text="Delete Product", command=delete_product, width=14, bg="#e74c3c", fg="white", font=("Arial", 12, "bold")).grid(row=0, column=2, padx=6)

# Search Frame
search_frame = tk.Frame(root, bg="#f5f6fa")
search_frame.pack(pady=6)
search_var = tk.StringVar()
tk.Entry(search_frame, textvariable=search_var, width=48, font=("Arial", 12)).grid(row=0, column=0, padx=6)
tk.Button(search_frame, text="Search", command=lambda: search_product(search_var.get()), bg="#9b59b6", fg="white", font=("Arial", 12, "bold")).grid(row=0, column=1, padx=6)
tk.Button(search_frame, text="Refresh", command=fetch_products, bg="#95a5a6", fg="white", font=("Arial", 12, "bold")).grid(row=0, column=2, padx=6)

# Table Frame
frame_table = tk.Frame(root, bg="#f5f6fa")
frame_table.pack(padx=20, pady=10, fill="both", expand=True)
columns = ("ID", "Name", "Price", "Stock")
table = ttk.Treeview(frame_table, columns=columns, show="headings", height=14)
table.pack(side="left", fill="both", expand=True)
scroll = ttk.Scrollbar(frame_table, orient="vertical", command=table.yview)
scroll.pack(side="right", fill="y")
table.configure(yscrollcommand=scroll.set)
style = ttk.Style()
style.theme_use("clam")
style.configure("Treeview.Heading", font=("Helvetica", 12, "bold"), foreground="#fff", background="#2f3640")
style.configure("Treeview", font=("Arial", 11), rowheight=26, background="#ffffff", fieldbackground="#ffffff")
style.map("Treeview", background=[("selected", "#487eb0")], foreground=[("selected", "white")])
for col, w in zip(columns, [60, 420, 100, 100]):
    table.heading(col, text=col if col != "Name" else "Product Name")
    table.column(col, width=w, anchor="center" if col != "Name" else "w")
table.tag_configure("low", background="#fdecea")
table.bind("<ButtonRelease-1>", select_row)

# Footer
tk.Label(root, text="📊 Inventory & Billing System | Developed by Your Team", font=("Helvetica", 10), bg="#f5f6fa", fg="#718093").pack(pady=8)

# Load Data
fetch_products()

# Start GUI
root.mainloop()