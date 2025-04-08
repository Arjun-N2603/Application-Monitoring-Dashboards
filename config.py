import os

# Secret key for sessions
SECRET_KEY = 'your-secret-key-here'  # Change this to a secure random key

# Database configuration
DATABASE_HOST = 'localhost'
DATABASE_USER = 'root' 
DATABASE_PASSWORD = 'Arjun@2004'  
DATABASE_NAME = 'university_assignment_portal'

# File upload configuration
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'uploads')
ALLOWED_EXTENSIONS = {'pdf', 'doc', 'docx', 'txt', 'zip', 'rar', 'py', 'java', 'cpp'}

# Create uploads directory if it doesn't exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# File Upload Settings
MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file size