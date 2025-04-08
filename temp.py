from flask import Flask, request, jsonify, session, redirect, url_for, send_from_directory, render_template
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import mysql.connector
from config import (SECRET_KEY, DATABASE_HOST, DATABASE_USER, DATABASE_PASSWORD, 
                   DATABASE_NAME, UPLOAD_FOLDER, ALLOWED_EXTENSIONS)
import datetime
import os
from functools import wraps

app = Flask(__name__)
app.secret_key = SECRET_KEY  # Set a strong secret key!
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max-limit

# Database connection 
mydb = mysql.connector.connect(
    host=DATABASE_HOST,
    user=DATABASE_USER,
    password=DATABASE_PASSWORD,
    database=DATABASE_NAME
)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

"""
University Assignment Portal - Route Definitions

This module contains all the route handlers for the assignment portal, organized by:
1. Common Routes (register, login, logout)
2. Admin Routes (course management, enrollment approval)
3. Professor Routes (assignment creation, grading)
4. Student Routes (assignment submission, course enrollment)

Each route is protected with proper authentication and role verification.
"""

# Authentication Middleware
def login_required(f):
    """Decorator to verify user authentication for protected routes."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'message': 'Please login to access this page', 'redirect': '/login'}), 401
        return f(*args, **kwargs)
    return decorated_function

# ============ Common Routes ============
@app.route('/register', methods=['POST'])
def register():
    """Handle new user registration for all roles."""
    print(request.url) 
    data = request.get_json()
    print(data)
    username = data.get('username')
    password = data.get('password')

    first_name = data.get('first_name')
    last_name = data.get('last_name')
    email = data.get('email')

    role = data.get('role')

    # data validation  
    if not all([username, password, first_name, last_name, email, role]):
        return jsonify({'message': 'Missing required fields'}), 400

    hashed_password = generate_password_hash(password, method='pbkdf2:sha256')

    cursor = mydb.cursor()
    try:
        cursor.execute("INSERT INTO User (Username, Password, FirstName, LastName, Email, Role) VALUES (%s, %s, %s, %s, %s, %s)",
                       (username, hashed_password, first_name, last_name, email, role))
        mydb.commit()
        return jsonify({'message': 'User registered successfully'}), 201
    except mysql.connector.Error as err:
        print(f"Error during registration: {err}")
        return jsonify({'message': 'Registration failed'}), 500

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Authenticate users and create session."""
    if request.method == 'GET':
        return render_template('login.html')  # Render login page for GET requests

    data = request.get_json()
    username = data.get('username')
    password = data.get('password')

    if not all([username, password]):
        return jsonify({'message': 'Missing username or password'}), 400

    cursor = mydb.cursor(dictionary=True)
    try:
        cursor.execute("SELECT * FROM User WHERE Username = %s", (username,))
        user = cursor.fetchone()

        if user and check_password_hash(user['Password'], password):
            session['user_id'] = user['UserID']
            session['role'] = user['Role']
            session['username'] = user['Username']  # Store username in session

            response_data = {
                'message': 'Login successful',
                'user_id': user['UserID'],
                'role': user['Role']
            }

            # Add admin redirect
            if user['Role'] == 'admin':
                response_data['redirect'] = '/admin-dashboard'
            elif user['Role'] == 'professor':
                response_data['redirect'] = '/professor-dashboard'
            else:
                response_data['redirect'] = '/student-dashboard'

            return jsonify(response_data), 200
        else:
            return jsonify({'message': 'Invalid credentials'}), 401
    except mysql.connector.Error as err:
        print(f"Error during login: {err}")
        return jsonify({'message': 'Login failed'}), 500

@app.route('/logout')
@login_required
def logout():
    """End user session and logout."""
    print(request.url) 
    session.pop('user_id', None)
    return jsonify({'message': 'Logged out'}), 200

# ============ Admin Routes ============
@app.route('/admin-dashboard')
@login_required
def admin_dashboard():
    """Admin dashboard showing system statistics and recent activities."""
    if session.get('role') != 'admin':
        return jsonify({'message': 'Only admins can access this route'}), 403

    if 'user_id' not in session or session.get('role') != 'admin':
        return jsonify({'message': 'Unauthorized'}), 401

    cursor = mydb.cursor(dictionary=True)
    try:
        # Get system statistics
        cursor.execute("""
            SELECT 
                (SELECT COUNT(*) FROM User WHERE Role = 'student') as student_count,
                (SELECT COUNT(*) FROM User WHERE Role = 'professor') as professor_count,
                (SELECT COUNT(*) FROM Course) as course_count,
                (SELECT COUNT(*) FROM Assignment) as assignment_count
        """)
        stats = cursor.fetchone()

        # Get recent activities
        cursor.execute("""
            (SELECT 'New User' as type, Username as detail, CreatedAt as timestamp
             FROM User ORDER BY UserID DESC LIMIT 5)
            UNION ALL
            (SELECT 'New Course' as type, CourseName as detail, CreatedAt as timestamp
             FROM Course ORDER BY CourseID DESC LIMIT 5)
            ORDER BY timestamp DESC LIMIT 10
        """)
        recent_activities = cursor.fetchall()

        return jsonify({
            'stats': stats,
            'recent_activities': recent_activities,
            'admin_name': session.get('username')
        }), 200
    except mysql.connector.Error as err:
        return jsonify({'message': 'Error fetching dashboard data'}), 500

@app.route('/admin/courses/create', methods=['POST'])
@login_required
def admin_create_course():
    """Create new courses and assign professors."""
    if session.get('role') != 'admin':
        return jsonify({'message': 'Only admins can access this route'}), 403

    if 'user_id' not in session or session.get('role') != 'admin':
        return jsonify({'message': 'Unauthorized'}), 401

    data = request.get_json()
    course_name = data.get('course_name')
    course_code = data.get('course_code')
    instructor_id = data.get('instructor_id')  # Admin selects professor
    year = data.get('year')
    semester = data.get('semester')

    if not all([course_name, course_code, instructor_id, year, semester]):
        return jsonify({'message': 'Missing required fields'}), 400

    cursor = mydb.cursor(dictionary=True)
    try:
        # Verify if selected instructor is actually a professor
        cursor.execute("SELECT Role FROM User WHERE UserID = %s", (instructor_id,))
        user = cursor.fetchone()
        if not user or user['Role'] != 'professor':
            return jsonify({'message': 'Selected user is not a professor'}), 400

        cursor.execute("""
            INSERT INTO Course (CourseName, CourseCode, InstructorID, Year, Semester) 
            VALUES (%s, %s, %s, %s, %s)
        """, (course_name, course_code, instructor_id, year, semester))
        mydb.commit()
        return jsonify({'message': 'Course created successfully', 'course_id': cursor.lastrowid}), 201
    except mysql.connector.Error as err:
        print(f"Error creating course: {err}")
        return jsonify({'message': 'Failed to create course'}), 500

@app.route('/admin/enrollment/approve/<int:request_id>', methods=['POST'])
@login_required
def approve_enrollment(request_id):
    """Process student enrollment requests."""
    if session.get('role') != 'admin':
        return jsonify({'message': 'Only admins can approve enrollments'}), 403

    cursor = mydb.cursor(dictionary=True)
    try:
        # First get the enrollment request details
        cursor.execute("""
            SELECT StudentID, CourseID, Status 
            FROM EnrollmentRequest 
            WHERE RequestID = %s
        """, (request_id,))
        
        request = cursor.fetchone()
        if not request:
            return jsonify({'message': 'Enrollment request not found'}), 404
            
        if request['Status'] != 'pending':
            return jsonify({'message': 'Request has already been processed'}), 400

        # Start transaction
        cursor.execute("START TRANSACTION")
        
        # Update request status to approved
        cursor.execute("""
            UPDATE EnrollmentRequest 
            SET Status = 'approved', ProcessedDate = NOW() 
            WHERE RequestID = %s
        """, (request_id,))

        # Create new enrollment
        cursor.execute("""
            INSERT INTO Enrollment (StudentID, CourseID, EnrollmentDate)
            VALUES (%s, %s, NOW())
        """, (request['StudentID'], request['CourseID']))

        # Create notification for student
        cursor.execute("""
            INSERT INTO Notification (UserID, Message, Timestamp)
            SELECT %s, 
                   CONCAT('Your enrollment request for course ', c.CourseName, ' has been approved'),
                   NOW()
            FROM Course c
            WHERE c.CourseID = %s
        """, (request['StudentID'], request['CourseID']))

        cursor.execute("COMMIT")
        return jsonify({'message': 'Enrollment request approved successfully'}), 200

    except mysql.connector.Error as err:
        cursor.execute("ROLLBACK")
        print(f"Error processing enrollment: {err}")
        return jsonify({'message': 'Failed to process enrollment request'}), 500

# ============ Professor Routes ============
@app.route('/professor-dashboard')
@login_required
def professor_dashboard():
    """Professor dashboard showing assigned courses and student counts."""
    if session.get('role') != 'professor':
        return jsonify({'message': 'Only professors can access this route'}), 403

    if 'user_id' not in session or session.get('role') != 'professor':
        return jsonify({'message': 'Unauthorized'}), 401

    cursor = mydb.cursor(dictionary=True)
    try:
        # Fetch professor's courses
        cursor.execute("""
            SELECT c.*, 
                   COUNT(DISTINCT a.AssignmentID) as assignment_count,
                   COUNT(DISTINCT e.StudentID) as enrolled_students
            FROM Course c
            LEFT JOIN Assignment a ON c.CourseID = a.CourseID
            LEFT JOIN Enrollment e ON c.CourseID = e.CourseID
            WHERE c.InstructorID = %s
            GROUP BY c.CourseID
        """, (session['user_id'],))
        courses = cursor.fetchall()

        return jsonify({
            'courses': courses,
            'professor_name': session.get('username'),
        }), 200
    except mysql.connector.Error as err:
        return jsonify({'message': 'Error fetching dashboard data'}), 500

@app.route('/courses/<int:course_id>/assignments', methods=['POST'])
@login_required
def create_assignment(course_id):
    """Create new assignments for a course."""
    if session.get('role') != 'professor':
        return jsonify({'message': 'Only professors can access this route'}), 403

    if 'user_id' not in session:
        return jsonify({'message': 'Unauthorized'}), 401

    data = request.get_json()
    title = data.get('title')
    description = data.get('description')
    due_date_str = data.get('due_date')  # Get due_date as a string

    # Data validation
    if not all([title, due_date_str]):
        return jsonify({'message': 'Missing required fields'}), 400

    # Parse the due_date string into a datetime object (compatible with MySQL DATETIME)
    try:
        due_date = datetime.datetime.strptime(due_date_str, '%Y-%m-%d %H:%M:%S')  # Example format: '2024-12-31 23:59:59'
    except ValueError:
        return jsonify({'message': 'Invalid due_date format. Please use YYYY-MM-DD HH:MM:SS'}), 400

    # Get the role of the logged-in user
    cursor = mydb.cursor(dictionary=True)
    try:
        cursor.execute("SELECT Role FROM User WHERE UserID = %s", (session['user_id'],))
        user = cursor.fetchone()
        if user and user['Role'] == 'professor':
            # Only allow professors to create assignments
            cursor.execute("INSERT INTO Assignment (CourseID, Title, Description, DueDate) VALUES (%s, %s, %s, %s)",
                           (course_id, title, description, due_date))  # Use the parsed due_date object
            mydb.commit()
            return jsonify({'message': 'Assignment created successfully'}), 201
        else:
            return jsonify({'message': 'Only professors can create assignments'}), 403  # Forbidden
    except mysql.connector.Error as err:
        print(f"Error creating assignment: {err}")
        return jsonify({'message': 'Failed to create assignment'}), 500

@app.route('/assignments/<int:assignment_id>/submissions', methods=['GET'])
@login_required
def get_assignment_submissions(assignment_id):
    """View all submissions for an assignment."""
    if session.get('role') != 'professor':
        return jsonify({'message': 'Only professors can access this route'}), 403

    if 'user_id' not in session or session.get('role') != 'professor':
        return jsonify({'message': 'Unauthorized'}), 401

    cursor = mydb.cursor(dictionary=True)
    try:
        # Verify professor teaches this course
        cursor.execute("""
            SELECT c.CourseID FROM Course c
            JOIN Assignment a ON c.CourseID = a.CourseID
            WHERE a.AssignmentID = %s AND c.InstructorID = %s
        """, (assignment_id, session['user_id']))
        
        if not cursor.fetchone():
            return jsonify({'message': 'Not authorized to view these submissions'}), 403

        # Get all submissions for this assignment
        cursor.execute("""
            SELECT s.*, u.FirstName, u.LastName, u.Username
            FROM Submission s
            JOIN User u ON s.StudentID = u.UserID
            WHERE s.AssignmentID = %s
            ORDER BY s.SubmissionDate DESC
        """, (assignment_id,))
        
        submissions = cursor.fetchall()
        return jsonify({'submissions': submissions}), 200
    except mysql.connector.Error as err:
        print(f"Error fetching submissions: {err}")
        return jsonify({'message': 'Failed to fetch submissions'}), 500

@app.route('/submissions/<int:submission_id>/grade', methods=['POST'])
@login_required
def grade_submission(submission_id):
    """Grade and provide feedback on student submissions."""
    if session.get('role') != 'professor':
        return jsonify({'message': 'Only professors can access this route'}), 403

    if 'user_id' not in session or session.get('role') != 'professor':
        return jsonify({'message': 'Unauthorized'}), 401

    data = request.get_json()
    grade = data.get('grade')
    feedback = data.get('feedback')

    if not grade:
        return jsonify({'message': 'Grade is required'}), 400

    cursor = mydb.cursor(dictionary=True)
    try:
        # Verify professor teaches this course
        cursor.execute("""
            SELECT c.CourseID 
            FROM Course c
            JOIN Assignment a ON c.CourseID = a.CourseID
            JOIN Submission s ON a.AssignmentID = s.AssignmentID
            WHERE s.SubmissionID = %s AND c.InstructorID = %s
        """, (submission_id, session['user_id']))

        if not cursor.fetchone():
            return jsonify({'message': 'Not authorized to grade this submission'}), 403

        # Update the submission with grade and feedback
        cursor.execute("""
            UPDATE Submission 
            SET Grade = %s, Feedback = %s, GradedDate = NOW()
            WHERE SubmissionID = %s
        """, (grade, feedback, submission_id))
        
        mydb.commit()

        # Create notification for student
        cursor.execute("""
            INSERT INTO Notification (UserID, Message, Timestamp)
            SELECT s.StudentID, 
                   CONCAT('Your submission for assignment "', a.Title, '" has been graded'), 
                   NOW()
            FROM Submission s
            JOIN Assignment a ON s.AssignmentID = a.AssignmentID
            WHERE s.SubmissionID = %s
        """, (submission_id,))
        
        mydb.commit()
        return jsonify({'message': 'Submission graded successfully'}), 200
    except mysql.connector.Error as err:
        print(f"Error grading submission: {err}")
        return jsonify({'message': 'Failed to grade submission'}), 500

# ============ Student Routes ============
@app.route('/student-dashboard')
@login_required
def student_dashboard():
    """Student dashboard showing enrolled courses and available courses."""
    if session.get('role') != 'student':
        return jsonify({'message': 'Only students can access this route'}), 403

    if 'user_id' not in session or session.get('role') != 'student':
        return jsonify({'message': 'Unauthorized'}), 401

    cursor = mydb.cursor(dictionary=True)
    try:
        # Fetch enrolled courses and available courses
        cursor.execute("""
            SELECT c.*, 
                   u.FirstName as instructor_name,
                   CASE WHEN e.StudentID IS NOT NULL THEN TRUE ELSE FALSE END as is_enrolled
            FROM Course c
            JOIN User u ON c.InstructorID = u.UserID
            LEFT JOIN Enrollment e ON c.CourseID = e.CourseID AND e.StudentID = %s
        """, (session['user_id'],))
        courses = cursor.fetchall()

        return jsonify({
            'enrolled_courses': [c for c in courses if c['is_enrolled']],
            'available_courses': [c for c in courses if not c['is_enrolled']],
            'student_name': session.get('username'),
        }), 200
    except mysql.connector.Error as err:
        return jsonify({'message': 'Error fetching dashboard data'}), 500

@app.route('/assignments/<int:assignment_id>/submit', methods=['POST'])
@login_required
def submit_assignment(assignment_id):
    """Submit assignment files for grading."""
    if session.get('role') != 'student':
        return jsonify({'message': 'Only students can access this route'}), 403

    if 'user_id' not in session:
        return jsonify({'message': 'Unauthorized'}), 401

    cursor = mydb.cursor(dictionary=True)
    try:
        # First verify if user is a student
        cursor.execute("SELECT Role FROM User WHERE UserID = %s", (session['user_id'],))
        user = cursor.fetchone()
        if user['Role'] != 'student':
            return jsonify({'message': 'Only students can submit assignments'}), 403

        # Rest of the submission logic
        if 'file' not in request.files:
            return jsonify({'message': 'No file part'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'message': 'No selected file'}), 400

        if file and allowed_file(file.filename):
            # Create submission directory if it doesn't exist
            submission_dir = os.path.join(app.config['UPLOAD_FOLDER'], f'assignment_{assignment_id}')
            os.makedirs(submission_dir, exist_ok=True)
            
            # Secure filename and save file
            filename = secure_filename(f"{session['user_id']}_{file.filename}")
            file_path = os.path.join(submission_dir, filename)
            file.save(file_path)

            cursor = mydb.cursor(dictionary=True)
            try:
                # Record the submission in database
                cursor.execute("""
                    INSERT INTO Submission (AssignmentID, StudentID, SubmissionPath, SubmissionDate)
                    VALUES (%s, %s, %s, NOW())
                """, (assignment_id, session['user_id'], file_path))
                mydb.commit()
                return jsonify({'message': 'Assignment submitted successfully'}), 201
            except mysql.connector.Error as err:
                if err.errno == 1644:  # Custom error from trigger
                    return jsonify({'message': str(err)}), 403
                print(f"Error recording submission: {err}")
                return jsonify({'message': 'Failed to record submission'}), 500

        return jsonify({'message': 'File type not allowed'}), 400

    except mysql.connector.Error as err:
        if err.errno == 1644:  # Custom error from trigger
            return jsonify({'message': str(err)}), 403
        print(f"Error submitting assignment: {err}")
        return jsonify({'message': 'Failed to submit assignment'}), 500

@app.route('/student/courses/request/<int:course_id>', methods=['POST'])
@login_required
def request_enrollment(course_id):
    """Request enrollment in a course."""
    if session.get('role') != 'student':
        return jsonify({'message': 'Only students can access this route'}), 403

    if 'user_id' not in session or session.get('role') != 'student':
        return jsonify({'message': 'Unauthorized'}), 401
    
    cursor = mydb.cursor(dictionary=True)
    try:
        # Check if already enrolled or requested
        cursor.execute("""
            SELECT 1 FROM EnrollmentRequest 
            WHERE StudentID = %s AND CourseID = %s AND Status = 'pending'
        """, (session['user_id'], course_id))
        if cursor.fetchone():
            return jsonify({'message': 'Enrollment request already pending'}), 400

        cursor.execute("""
            INSERT INTO EnrollmentRequest (StudentID, CourseID, RequestDate, Status)
            VALUES (%s, %s, NOW(), 'pending')
        """, (session['user_id'], course_id))
        mydb.commit()
        return jsonify({'message': 'Enrollment request submitted successfully'}), 201
    except mysql.connector.Error as err:
        return jsonify({'message': 'Error submitting enrollment request'}), 500

# Add @login_required to all remaining routes and add role checks
@app.route('/courses/<int:course_id>/materials', methods=['POST'])
@login_required
def upload_course_material(course_id):
    if session.get('role') != 'professor':
        return jsonify({'message': 'Only professors can access this route'}), 403

    if 'user_id' not in session or session.get('role') != 'professor':
        return jsonify({'message': 'Unauthorized'}), 401

    cursor = mydb.cursor(dictionary=True)
    try:
        if 'file' not in request.files:
            return jsonify({'message': 'No file part'}), 400
        
        file = request.files['file']
        description = request.form.get('description', '')

        if file.filename == '':
            return jsonify({'message': 'No selected file'}), 400

        if file and allowed_file(file.filename):
            # Create materials directory if it doesn't exist
            materials_dir = os.path.join(app.config['UPLOAD_FOLDER'], f'course_{course_id}')
            os.makedirs(materials_dir, exist_ok=True)
            
            filename = secure_filename(file.filename)
            file_path = os.path.join(materials_dir, filename)
            file.save(file_path)

            try:
                # Set current user for the trigger
                cursor.execute("SET @current_user_id = %s", (session['user_id'],))
                
                # Record the material in database
                cursor.execute("""
                    INSERT INTO CourseMaterial (CourseID, FilePath, Description, UploadDate)
                    VALUES (%s, %s, %s, NOW())
                """, (course_id, file_path, description))
                mydb.commit()
                return jsonify({'message': 'Material uploaded successfully'}), 201
            except mysql.connector.Error as err:
                if err.errno == 1644:  # Custom error from trigger
                    return jsonify({'message': str(err)}), 403
                print(f"Error recording material: {err}")
                return jsonify({'message': 'Failed to record material'}), 500

        return jsonify({'message': 'File type not allowed'}), 400

    except mysql.connector.Error as err:
        print(f"Error uploading material: {err}")
        return jsonify({'message': 'Failed to upload material'}), 500

@app.route('/submissions/<int:submission_id>/download', methods=['GET'])
@login_required
def download_submission(submission_id):
    if session.get('role') != 'professor':
        return jsonify({'message': 'Only professors can access this route'}), 403

    if 'user_id' not in session or session.get('role') != 'professor':
        return jsonify({'message': 'Unauthorized'}), 401

    cursor = mydb.cursor(dictionary=True)
    try:
        # Get submission file path and verify authorization
        cursor.execute("""
            SELECT s.SubmissionPath, s.AssignmentID
            FROM Submission s
            JOIN Assignment a ON s.AssignmentID = a.AssignmentID
            JOIN Course c ON a.CourseID = c.CourseID
            WHERE s.SubmissionID = %s AND c.InstructorID = %s
        """, (submission_id, session['user_id']))
        
        submission = cursor.fetchone()
        if not submission:
            return jsonify({'message': 'Submission not found or unauthorized'}), 404

        return send_from_directory(
            directory=os.path.dirname(submission['SubmissionPath']),
            path=os.path.basename(submission['SubmissionPath'])
        )
    except mysql.connector.Error as err:
        print(f"Error downloading submission: {err}")
        return jsonify({'message': 'Failed to download submission'}), 500

if __name__ == '__main__':
    app.run(debug=True)