import mysql.connector
import routes  # Import the routes module

from config import DATABASE_HOST, DATABASE_USER, DATABASE_PASSWORD, DATABASE_NAME

try:
    mydb = mysql.connector.connect(
        host=DATABASE_HOST,
        user=DATABASE_USER,
        password=DATABASE_PASSWORD,
        database=DATABASE_NAME
    )
    cursor = mydb.cursor()

    print("Database connection successful!")

    # Test the connection (optional):
    cursor.execute("SELECT VERSION()")
    data = cursor.fetchone()
    print("Database version:", data)

except mysql.connector.Error as err:
    print(f"Database connection failed: {err}")

app = routes.app  # Get the app instance from routes.py

if __name__ == '__main__':
    app.run(debug=True)