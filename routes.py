from flask import Flask, request, jsonify, session, redirect, url_for, send_from_directory, render_template, g
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import mysql.connector
import datetime
import os
from functools import wraps
from config import (SECRET_KEY, DATABASE_HOST, DATABASE_USER, DATABASE_PASSWORD, 
                   DATABASE_NAME, UPLOAD_FOLDER, ALLOWED_EXTENSIONS)
from kafka import KafkaProducer
import json
import time
import logging
from flask_socketio import SocketIO, emit

app = Flask(__name__)
app.secret_key = SECRET_KEY  # Set a strong secret key!
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max-limit

# Initialize SocketIO
socketio = SocketIO(app)

# Database connection 
try:
    mydb = mysql.connector.connect(
        host=DATABASE_HOST,
        user=DATABASE_USER,
        password=DATABASE_PASSWORD,
        database=DATABASE_NAME
    )
    print("Database connection established successfully.")
except mysql.connector.Error as err:
    print(f"Error connecting to the database: {err}")
    exit(1)  # Exit if the database connection fails

# Kafka Configuration
KAFKA_BOOTSTRAP_SERVERS = 'localhost:9092'
API_ACCESS_TOPIC = 'api_access_logs'

# Initialize Kafka Producer
try:
    producer = KafkaProducer(
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        value_serializer=lambda v: json.dumps(v).encode('utf-8')
    )
    print("Kafka producer initialized successfully.")
except Exception as e:
    print(f"Error initializing Kafka producer: {e}")
    exit(1)  # Exit if Kafka producer initialization fails

# Middleware to log all requests and responses
@app.before_request
def log_request():
    """Log incoming requests."""
    g.start_time = time.time()  # Track request start time
    logging.info(f"Request received: {request.method} {request.path}")

@app.after_request
def log_response(response):
    """Log outgoing responses."""
    response_time = time.time() - g.start_time
    log_message = {
        'timestamp': time.time(),
        'endpoint': request.path,
        'method': request.method,
        'status_code': response.status_code,
        'response_time': response_time,
        'user_id': session.get('user_id', 'anonymous'),
        'role': session.get('role', 'unknown')
    }
    try:
        producer.send(API_ACCESS_TOPIC, log_message)  # Send log to Kafka
    except Exception as e:
        logging.error(f"Failed to send log to Kafka: {e}")
    return response

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

# Utility function to ensure MySQL connection is active
def get_db_connection():
    global mydb
    if not mydb.is_connected():
        mydb = mysql.connector.connect(
            host=DATABASE_HOST,
            user=DATABASE_USER,
            password=DATABASE_PASSWORD,
            database=DATABASE_NAME
        )
    return mydb

# Modify the root route to handle role-based redirection
@app.route('/')
def index():
    if 'user_id' in session:
        role = session.get('role')
        if role == 'admin':
            return redirect(url_for('admin_dashboard_page'))
        elif role == 'professor':
            return redirect(url_for('professor_dashboard_page'))
        else:
            return redirect(url_for('student_dashboard_page'))
    return redirect(url_for('login_page'))

# Add new routes for serving HTML pages
@app.route('/login', methods=['GET'])
def login_page():
    if 'user_id' in session:
        return redirect(url_for('index'))
    return render_template('login.html')

@app.route('/register', methods=['GET'])
def register_page():
    if 'user_id' in session:
        return redirect(url_for('index'))
    return render_template('register.html')

# Add new routes for serving dashboard pages
@app.route('/admin-dashboard-page')
@login_required
def admin_dashboard_page():
    if session.get('role') != 'admin':
        return redirect(url_for('index'))
    return render_template('admin_dashboard.html')

@app.route('/professor-dashboard-page')
@login_required
def professor_dashboard_page():
    if session.get('role') != 'professor':
        return redirect(url_for('index'))
    return render_template('professor_dashboard.html')

@app.route('/student-dashboard-page')
@login_required
def student_dashboard_page():
    if session.get('role') != 'student':
        return redirect(url_for('index'))
    return render_template('student_dashboard.html')

@app.route('/api/assignments/upload', methods=['POST'])
@login_required
def upload_assignment():
    """Handle assignment file uploads from professors."""
    if session.get('role') != 'professor':
        return jsonify({'success': False, 'message': 'Only professors can upload assignments'}), 403

    try:
        # Verify form data
        if 'file' not in request.files:
            return jsonify({'success': False, 'message': 'No file uploaded'}), 400
            
        file = request.files['file']
        if file.filename == '':
            return jsonify({'success': False, 'message': 'No file selected'}), 400

        title = request.form.get('title')
        description = request.form.get('description')
        due_date = request.form.get('due_date')
        course_id = request.form.get('course_id')

        if not all([title, description, due_date, course_id]):
            return jsonify({'success': False, 'message': 'Missing required fields'}), 400

        cursor = mydb.cursor(dictionary=True)
        
        # Verify professor teaches this course
        cursor.execute("""
            SELECT 1 FROM Course 
            WHERE CourseID = %s AND InstructorID = %s
        """, (course_id, session['user_id']))
        
        if not cursor.fetchone():
            return jsonify({'success': False, 'message': 'You can only upload assignments to your courses'}), 403

        if file and allowed_file(file.filename):
            try:
                # Create paths for professor uploads
                assignment_base_dir = os.path.join(
                    app.config['UPLOAD_FOLDER'],
                    'assignments'  # Base directory for all assignments
                )
                
                # Create unique assignment directory
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                safe_title = "".join(c for c in title if c.isalnum() or c in (' ', '-', '_')).rstrip()
                assignment_dir = os.path.join(
                    assignment_base_dir,
                    f'assignment_{timestamp}_{safe_title}'  # Unique assignment directory
                )
                
                # Create professor uploads directory within assignment directory
                professor_upload_dir = os.path.join(assignment_dir, 'professor_upload')
                os.makedirs(professor_upload_dir, exist_ok=True)
                
                # Save professor's file
                filename = secure_filename(file.filename)
                file_path = os.path.join(professor_upload_dir, filename)
                file.save(file_path)

                # Create directory for student submissions
                student_submissions_dir = os.path.join(assignment_dir, 'student_submissions')
                os.makedirs(student_submissions_dir, exist_ok=True)

                # Save assignment record with the assignment directory path
                cursor.execute("""
                    INSERT INTO Assignment (CourseID, Title, Description, DueDate, FilePath, CreatedBy, CreatedAt)
                    VALUES (%s, %s, %s, %s, %s, %s, NOW())
                """, (course_id, title, description, due_date, assignment_dir, session['user_id']))
                
                mydb.commit()

                # Create notification for enrolled students
                cursor.execute("""
                    INSERT INTO Notification (UserID, Message, Timestamp)
                    SELECT e.StudentID, 
                           CONCAT('New assignment posted in ', c.CourseName, ': ', %s),
                           NOW()
                    FROM Enrollment e
                    JOIN Course c ON e.CourseID = c.CourseID
                    WHERE e.CourseID = %s AND e.Status = 'active'
                """, (title, course_id))
                
                mydb.commit()
                
                return jsonify({
                    'success': True,
                    'message': 'Assignment uploaded successfully',
                    'assignment_id': cursor.lastrowid
                }), 201
            
            except OSError as e:
                print(f"OS error: {e}")
                return jsonify({'success': False, 'message': 'Failed to save file'}), 500
        
        return jsonify({'success': False, 'message': 'Invalid file type'}), 400

    except mysql.connector.Error as err:
        print(f"Database error: {err}")
        return jsonify({'success': False, 'message': 'Database error occurred'}), 500
    except Exception as e:
        print(f"Error uploading assignment: {e}")
        return jsonify({'success': False, 'message': 'Failed to upload assignment'}), 500


# ============ Common Routes ============
# Modify existing register route to handle both form and API requests
@app.route('/register', methods=['POST'])
def register():
    """Handle new user registration for all roles."""
    if request.is_json:
        data = request.get_json()
    else:
        data = request.form

    username = data.get('username')
    password = data.get('password')
    first_name = data.get('firstName')
    last_name = data.get('lastName')
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
        
        if request.is_json:
            return jsonify({'message': 'User registered successfully'}), 201
        return redirect(url_for('login_page'))
    except mysql.connector.Error as err:
        print(f"Error during registration: {err}")
        return jsonify({'message': 'Registration failed'}), 500

# Modify login route to handle proper redirections
@app.route('/login', methods=['POST'])
def login():
    """Authenticate users and create session."""
    if request.is_json:
        data = request.get_json()
    else:
        data = request.form

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
            session['username'] = user['Username']

            # Redirect based on role
            if user['Role'] == 'admin':
                return redirect(url_for('admin_dashboard_page'))
            elif user['Role'] == 'professor':
                return redirect(url_for('professor_dashboard_page'))
            else:
                return redirect(url_for('student_dashboard_page'))
        else:
            return jsonify({'message': 'Invalid credentials'}), 401
    except mysql.connector.Error as err:
        print(f"Error during login: {err}")
        return jsonify({'message': 'Login failed'}), 500

# Modify logout route to redirect to login page
@app.route('/logout')
@login_required
def logout():
    """End user session and logout."""
    session.clear()
    return redirect(url_for('login_page'))

# Add error handlers
@app.errorhandler(404)
def not_found_error(error):
    return render_template('errors/404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    return render_template('errors/500.html'), 500

# ============ Admin Routes ============
@app.route('/admin-dashboard')
@login_required
def admin_dashboard():
    """Admin dashboard data API endpoint."""
    if session.get('role') != 'admin':
        return jsonify({'message': 'Only admins can access this route'}), 403

    # Ensure the database connection is active
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    try:
        # Stats query
        cursor.execute("""
            SELECT 
                (SELECT COUNT(*) FROM User WHERE Role = 'student' AND Active = 1) as student_count,
                (SELECT COUNT(*) FROM User WHERE Role = 'professor' AND Active = 1) as professor_count,
                (SELECT COUNT(*) FROM Course) as active_courses,
                (SELECT COUNT(*) FROM Assignment 
                 WHERE DueDate > CURRENT_TIMESTAMP 
                 AND Status = 'active') as active_assignments
        """)
        stats = cursor.fetchone()

        # Courses query with proper joins and GROUP BY
        cursor.execute("""
            SELECT 
                c.CourseID,
                c.CourseCode,
                c.CourseName,
                c.Year,
                c.Semester,
                CONCAT(u.FirstName, ' ', u.LastName) as InstructorName,
                COUNT(DISTINCT e.StudentID) as EnrolledCount
            FROM Course c
            LEFT JOIN User u ON c.InstructorID = u.UserID
            LEFT JOIN Enrollment e ON c.CourseID = e.CourseID
            GROUP BY c.CourseID, c.CourseCode, c.CourseName, c.Year, c.Semester, 
                     u.FirstName, u.LastName
            ORDER BY c.CourseCode
        """)
        courses = cursor.fetchall()

        # Add enrollment requests query
        cursor.execute("""
            SELECT 
                er.RequestID,
                DATE_FORMAT(er.RequestDate, '%Y-%m-%d %H:%i:%s') as RequestDate,
                er.Status,
                c.CourseName,
                c.CourseCode,
                CONCAT(u.FirstName, ' ', u.LastName) as StudentName
            FROM EnrollmentRequest er
            JOIN Course c ON er.CourseID = c.CourseID
            JOIN User u ON er.StudentID = u.UserID
            WHERE er.Status = 'pending'  # Add this condition
            ORDER BY er.RequestDate DESC
        """)
        enrollment_requests = cursor.fetchall()

        return jsonify({
            'stats': stats,
            'courses': courses,
            'enrollment_requests': enrollment_requests,
            'admin_name': session.get('username')
        }), 200

    except mysql.connector.Error as err:
        print(f"Error fetching dashboard data: {err}")
        return jsonify({'message': 'Error fetching dashboard data'}), 500

@app.route('/api/professors')
@login_required
def get_professors():
    """Get list of all professors for admin dashboard."""
    if session.get('role') != 'admin':
        return jsonify({'message': 'Unauthorized access'}), 403

    cursor = mydb.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT UserID, FirstName, LastName, Email 
            FROM User 
            WHERE Role = 'professor' AND Active = 1
            ORDER BY FirstName, LastName
        """)
        professors = cursor.fetchall()
        return jsonify({'professors': professors}), 200
    except mysql.connector.Error as err:
        print(f"Error fetching professors: {err}")
        return jsonify({'message': 'Failed to fetch professors'}), 500

# Update the existing admin_create_course route
@app.route('/admin/courses/create', methods=['POST'])
@login_required
def admin_create_course():
    """Create new courses and assign professors."""
    if session.get('role') != 'admin':
        return jsonify({'message': 'Only admins can create courses'}), 403

    data = request.get_json()
    required_fields = ['course_name', 'course_code', 'instructor_id', 'year', 'semester']
    
    if not all(field in data for field in required_fields):
        return jsonify({
            'success': False,
            'message': 'Missing required fields'
        }), 400

    # Validate semester is between 1 and 8
    try:
        semester = int(data['semester'])
        if not 1 <= semester <= 8:
            return jsonify({
                'success': False,
                'message': 'Semester must be between 1 and 8'
            }), 400
    except ValueError:
        return jsonify({
            'success': False,
            'message': 'Invalid semester value'
        }), 400

    cursor = mydb.cursor(dictionary=True)
    try:
        # Verify if selected instructor exists and is a professor
        cursor.execute("""
            SELECT UserID, Role 
            FROM User 
            WHERE UserID = %s AND Role = 'professor' AND Active = 1
        """, (data['instructor_id'],))
        
        if not cursor.fetchone():
            return jsonify({
                'success': False,
                'message': 'Selected instructor is not valid'
            }), 400

        # Create the course
        cursor.execute("""
            INSERT INTO Course (CourseName, CourseCode, InstructorID, Year, Semester) 
            VALUES (%s, %s, %s, %s, %s)
        """, (
            data['course_name'],
            data['course_code'],
            data['instructor_id'],
            data['year'],
            semester  # Now using the validated integer value
        ))
        
        mydb.commit()
        
        return jsonify({
            'success': True,
            'message': 'Course created successfully',
            'course_id': cursor.lastrowid
        }), 201

    except mysql.connector.Error as err:
        print(f"Error creating course: {err}")
        return jsonify({
            'success': False,
            'message': 'Failed to create course'
        }), 500

@app.route('/admin/enrollment/approve/<int:request_id>', methods=['POST'])
@login_required
def approve_enrollment(request_id):
    if session.get('role') != 'admin':
        return jsonify({'success': False, 'message': 'Only admins can approve enrollments'}), 403

    cursor = mydb.cursor(dictionary=True)
    try:
        # Initialize OUT parameters
        cursor.execute("SET @success = NULL, @message = NULL")

        # Call the stored procedure with MySQL session variables
        cursor.execute(f"CALL ProcessEnrollmentRequest({request_id}, {session['user_id']}, 'approve', @success, @message)")

        # Fetch OUT parameters
        cursor.execute("SELECT @success, @message")
        result = cursor.fetchone()
        success = result['@success']  # OUT success
        message = result['@message']  # OUT message

        mydb.commit()
        return jsonify({
            'success': bool(success),
            'message': message
        }), 200 if success else 400

    except mysql.connector.Error as err:
        print(f"Error processing enrollment: {err}")
        return jsonify({
            'success': False,
            'message': 'Failed to process enrollment request'
        }), 500

@app.route('/admin/enrollment/reject/<int:request_id>', methods=['POST'])
@login_required
def reject_enrollment(request_id):
    """Reject student enrollment request."""
    if session.get('role') != 'admin':
        return jsonify({'success': False, 'message': 'Only admins can reject enrollments'}), 403

    cursor = mydb.cursor(dictionary=True)
    try:
        cursor.execute("""
            UPDATE EnrollmentRequest 
            SET Status = 'rejected', ProcessedDate = NOW() 
            WHERE RequestID = %s AND Status = 'pending'
        """, (request_id,))
        
        if cursor.rowcount == 0:
            return jsonify({'success': False, 'message': 'Request not found or already processed'}), 404
        
        mydb.commit()
        return jsonify({'success': True, 'message': 'Enrollment request rejected successfully'}), 200

    except mysql.connector.Error as err:
        print(f"Error rejecting enrollment: {err}")
        return jsonify({'success': False, 'message': 'Failed to reject enrollment request'}), 500

# Add course deletion route
@app.route('/admin/courses/<int:course_id>/delete', methods=['POST'])
@login_required
def delete_course(course_id):
    if session.get('role') != 'admin':
        return jsonify({
            'success': False,
            'message': 'Only admins can delete courses'
        }), 403

    cursor = mydb.cursor(dictionary=True)
    try:
        # Start transaction
        cursor.execute("START TRANSACTION")
        
        # Check if course exists
        cursor.execute("SELECT CourseID, CourseName FROM Course WHERE CourseID = %s", (course_id,))
        course = cursor.fetchone()
        
        if not course:
            cursor.execute("ROLLBACK")
            return jsonify({
                'success': False,
                'message': 'Course not found'
            }), 404

        # Delete enrollments first
        cursor.execute("DELETE FROM Enrollment WHERE CourseID = %s", (course_id,))
        
        # Delete enrollment requests
        cursor.execute("DELETE FROM EnrollmentRequest WHERE CourseID = %s", (course_id,))
        
        
        # Delete assignments and their submissions
        cursor.execute("""
            DELETE s FROM Submission s
            INNER JOIN Assignment a ON s.AssignmentID = a.AssignmentID
            WHERE a.CourseID = %s
        """, (course_id,))
        
        cursor.execute("DELETE FROM Assignment WHERE CourseID = %s", (course_id,))
        
        # Finally delete the course
        cursor.execute("DELETE FROM Course WHERE CourseID = %s", (course_id,))
        
        # Create notification for affected users
        cursor.execute("""
            INSERT INTO Notification (UserID, Message, Timestamp)
            SELECT DISTINCT u.UserID, 
                   CONCAT('Course "', %s, '" has been deleted'),
                   NOW()
            FROM User u
            WHERE u.UserID IN (
                SELECT StudentID FROM Enrollment WHERE CourseID = %s
                UNION
                SELECT InstructorID FROM Course WHERE CourseID = %s
            )
        """, (course['CourseName'], course_id, course_id))
        
        cursor.execute("COMMIT")
        return jsonify({
            'success': True,
            'message': 'Course deleted successfully'
        }), 200

    except mysql.connector.Error as err:
        cursor.execute("ROLLBACK")
        print(f"Error deleting course: {err}")
        return jsonify({
            'success': False,
            'message': f'Failed to delete course: {str(err)}'
        }), 500

@app.route('/admin/courses/<int:course_id>/edit', methods=['POST'])
@login_required
def edit_course(course_id):
    """Edit existing course details."""
    if session.get('role') != 'admin':
        return jsonify({
            'success': False,
            'message': 'Only admins can edit courses'
        }), 403

    data = request.get_json()
    required_fields = ['course_name', 'course_code', 'instructor_id', 'year', 'semester']
    
    if not all(field in data for field in required_fields):
        return jsonify({
            'success': False,
            'message': 'Missing required fields'
        }), 400

    # Validate semester is between 1 and 8
    try:
        semester = int(data['semester'])
        if not 1 <= semester <= 8:
            return jsonify({
                'success': False,
                'message': 'Semester must be between 1 and 8'
            }), 400
    except ValueError:
        return jsonify({
            'success': False,
            'message': 'Invalid semester value'
        }), 400

    cursor = mydb.cursor(dictionary=True)
    try:
        # Verify if selected instructor exists and is a professor
        cursor.execute("""
            SELECT UserID, Role 
            FROM User 
            WHERE UserID = %s AND Role = 'professor' AND Active = 1
        """, (data['instructor_id'],))
        
        if not cursor.fetchone():
            return jsonify({
                'success': False,
                'message': 'Selected instructor is not valid'
            }), 400

        # Update the course
        cursor.execute("""
            UPDATE Course 
            SET CourseName = %s, 
                CourseCode = %s, 
                InstructorID = %s, 
                Year = %s, 
                Semester = %s
            WHERE CourseID = %s
        """, (
            data['course_name'],
            data['course_code'],
            data['instructor_id'],
            data['year'],
            semester,
            course_id
        ))
        
        mydb.commit()
        
        return jsonify({
            'success': True,
            'message': 'Course updated successfully'
        }), 200

    except mysql.connector.Error as err:
        print(f"Error updating course: {err}")
        return jsonify({
            'success': False,
            'message': 'Failed to update course'
        }), 500

# ============ Professor Routes ============
@app.route('/professor-dashboard')
@login_required
def professor_dashboard():
    if session.get('role') != 'professor':
        return jsonify({'message': 'Only professors can access this route'}), 403

    # Ensure the database connection is active
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    try:
        # Call GetProfessorDashboard procedure
        cursor.callproc('GetProfessorDashboard', (session['user_id'],))

        # Get results from all result sets
        results = []
        for result in cursor.stored_results():
            results.append(result.fetchall())

        # Map results to their respective data
        stats = results[0][0]  # First result set contains stats
        courses = results[1]   # Second result set contains courses
        submissions = results[2]  # Third result set contains submissions

        return jsonify({
            'stats': stats,
            'courses': courses,
            'submissions': submissions,
            'professor_name': session.get('username')
        }), 200

    except mysql.connector.Error as err:
        print(f"Error fetching dashboard data: {err}")
        return jsonify({'message': 'Error fetching dashboard data'}), 500

@app.route('/submissions/<int:submission_id>/grade', methods=['POST'])
@login_required
def grade_submission(submission_id):
    if session.get('role') != 'professor':
        return jsonify({'success': False, 'message': 'Only professors can grade submissions'}), 403

    data = request.get_json()
    grade = data.get('grade')
    feedback = data.get('feedback')

    if grade is None:
        return jsonify({'success': False, 'message': 'Grade is required'}), 400

    cursor = mydb.cursor(dictionary=True)
    try:
        # Call GradeSubmission procedure
        args = [submission_id, session['user_id'], grade, feedback, 0, '']  # Last two are OUT parameters
        result = cursor.callproc('GradeSubmission', args)
        
        success = result[4]  # Fifth parameter (OUT success)
        message = result[5]  # Sixth parameter (OUT message)
        
        mydb.commit()
        return jsonify({
            'success': success,
            'message': message
        }), 200 if success else 400

    except mysql.connector.Error as err:
        print(f"Error grading submission: {err}")
        return jsonify({'success': False, 'message': 'Failed to grade submission'}), 500

@app.route('/student-dashboard')
@login_required
def student_dashboard():
    if session.get('role') != 'student':
        return jsonify({'message': 'Only students can access this route'}), 403

    # Ensure the database connection is active
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    try:
        # Call GetStudentDashboard procedure
        cursor.callproc('GetStudentDashboard', (session['user_id'],))

        results = []
        for result in cursor.stored_results():
            results.append(result.fetchall())

        courses = results[0]  # First result set contains all courses
        assignments = results[1]  # Second result set contains assignments

        return jsonify({
            'enrolled_courses': [c for c in courses if c['is_enrolled']],
            'available_courses': [c for c in courses if not c['is_enrolled']],
            'upcoming_assignments': assignments,
            'student_name': session.get('username')
        }), 200
    except mysql.connector.Error as err:
        print(f"Error fetching dashboard data: {err}")
        return jsonify({'message': 'Error fetching dashboard data'}), 500

@app.route('/api/courses/<int:course_id>/details')
@login_required
def get_course_full_details(course_id):
    if session.get('role') != 'professor':
        return jsonify({'message': 'Unauthorized access'}), 403

    cursor = mydb.cursor(dictionary=True)
    try:
        # Get basic course info
        cursor.execute("""
            SELECT c.*, 
                   COUNT(DISTINCT e.StudentID) as enrolled_count,
                   COUNT(DISTINCT CASE WHEN a.DueDate > NOW() THEN a.AssignmentID END) as active_assignments
            FROM Course c
            LEFT JOIN Enrollment e ON c.CourseID = c.CourseID
            LEFT JOIN Assignment a ON c.CourseID = a.CourseID
            WHERE c.CourseID = %s AND c.InstructorID = %s
            GROUP BY c.CourseID
        """, (course_id, session['user_id']))
        
        course = cursor.fetchone()
        if not course:
            return jsonify({'message': 'Course not found or unauthorized'}), 404

        # Get enrolled students with their progress
        cursor.execute("""
            SELECT 
                u.UserID,
                CONCAT(u.FirstName, ' ', u.LastName) as name,
                COUNT(DISTINCT s.SubmissionID) as completed_assignments,
                COUNT(DISTINCT a.AssignmentID) as total_assignments,
                AVG(CASE WHEN s.Grade IS NOT NULL THEN s.Grade ELSE NULL END) as average_grade
            FROM User u
            JOIN Enrollment e ON u.UserID = e.StudentID
            LEFT JOIN Submission s ON u.UserID = s.StudentID
            LEFT JOIN Assignment a ON s.AssignmentID = a.AssignmentID
            WHERE e.CourseID = %s AND e.Status = 'active'
            GROUP BY u.UserID, u.FirstName, u.LastName
        """, (course_id,))
        
        students = cursor.fetchall()

        # Get course assignments
        cursor.execute("""
            SELECT 
                AssignmentID as id,
                Title as title,
                DueDate as due_date,
                (SELECT COUNT(*) FROM Submission s WHERE s.AssignmentID = a.AssignmentID) as submission_count,
                (SELECT COUNT(*) FROM Enrollment e WHERE e.CourseID = a.CourseID) as total_students
            FROM Assignment a
            WHERE CourseID = %s
            ORDER BY DueDate DESC
        """, (course_id,))
        
        assignments = cursor.fetchall()

        return jsonify({
            'name': course['CourseName'],
            'code': course['CourseCode'],
            'semester': course['Semester'],
            'year': course['Year'],
            'enrolled_count': course['enrolled_count'] or 0,
            'active_assignments': course['active_assignments'] or 0,
            'students': students,
            'assignments': assignments
        }), 200

    except mysql.connector.Error as err:
        print(f"Error fetching course details: {err}")
        return jsonify({'message': 'Failed to fetch course details'}), 500

# ============ Student Routes ============
@app.route('/assignments/<int:assignment_id>/submit', methods=['POST'])
@login_required
def submit_assignment(assignment_id):
    """Submit assignment files for grading."""
    if session.get('role') != 'student':
        return jsonify({'success': False, 'message': 'Only students can submit assignments'}), 403

    if 'file' not in request.files:
        return jsonify({'success': False, 'message': 'No file part'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'success': False, 'message': 'No selected file'}), 400

    cursor = mydb.cursor(dictionary=True)
    try:
        # Verify assignment exists and is still accepting submissions
        cursor.execute("""
            SELECT a.*, c.CourseID 
            FROM Assignment a
            JOIN Course c ON a.CourseID = c.CourseID
            WHERE a.AssignmentID = %s
        """, (assignment_id,))
        
        assignment = cursor.fetchone()
        if not assignment:
            return jsonify({'success': False, 'message': 'Assignment not found'}), 404

        # Verify student is enrolled in the course
        cursor.execute("""
            SELECT 1 FROM Enrollment 
            WHERE StudentID = %s AND CourseID = %s AND Status = 'active'
        """, (session['user_id'], assignment['CourseID']))
        
        if not cursor.fetchone():
            return jsonify({'success': False, 'message': 'You are not enrolled in this course'}), 403

        if file and allowed_file(file.filename):
            try:
                # Create submission directory if it doesn't exist
                submission_dir = os.path.join(
                    assignment['FilePath'],
                    'student_submissions',
                    f'student_{session["user_id"]}'
                )
                os.makedirs(submission_dir, exist_ok=True)

                # Create unique filename with timestamp
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = secure_filename(f"{timestamp}_{file.filename}")
                file_path = os.path.join(submission_dir, filename)
                
                # Save the file
                file.save(file_path)

                # Record the submission in database
                cursor.execute("""
                    INSERT INTO Submission 
                    (AssignmentID, StudentID, SubmissionPath, SubmissionDate) 
                    VALUES (%s, %s, %s, NOW())
                    ON DUPLICATE KEY UPDATE 
                    SubmissionPath = VALUES(SubmissionPath),
                    SubmissionDate = NOW()
                """, (assignment_id, session['user_id'], file_path))
                
                mydb.commit()

                return jsonify({
                    'success': True,
                    'message': 'Assignment submitted successfully'
                }), 200

            except Exception as e:
                print(f"Error saving submission: {e}")
                return jsonify({
                    'success': False,
                    'message': 'Failed to save submission'
                }), 500

        return jsonify({
            'success': False,
            'message': 'Invalid file type'
        }), 400

    except mysql.connector.Error as err:
        print(f"Database error: {err}")
        return jsonify({
            'success': False,
            'message': 'Database error occurred'
        }), 500

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
                if (err.errno == 1644):  # Custom error from trigger
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

@app.route('/course/<int:course_id>')
@login_required
def course_page(course_id):
    """Serve the course details page."""
    return render_template('course.html')

@app.route('/api/courses/<int:course_id>')
@login_required
def get_course_details(course_id):
    """Get detailed course information."""
    cursor = mydb.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT c.*, 
                   u.FirstName, u.LastName,
                   COUNT(DISTINCT e.StudentID) as enrolled_count
            FROM Course c
            JOIN User u ON c.InstructorID = u.UserID
            LEFT JOIN Enrollment e ON c.CourseID = e.CourseID
            WHERE c.CourseID = %s
            GROUP BY c.CourseID
        """, (course_id,))
        
        course = cursor.fetchone()
        if not course:
            return jsonify({'message': 'Course not found'}), 404

        return jsonify({
            'name': course['CourseName'],
            'code': course['CourseCode'],
            'instructor': f"{course['FirstName']} {course['LastName']}",
            'semester': course['Semester'],
            'year': course['Year'],
            'enrolled_count': course['enrolled_count']
        }), 200

    except mysql.connector.Error as err:
        print(f"Error fetching course details: {err}")
        return jsonify({'message': 'Failed to fetch course details'}), 500

@app.route('/api/user/role')
@login_required
def get_user_role():
    """Get the current user's role."""
    return jsonify({'role': session.get('role')}), 200

@app.route('/assignments')
@login_required
def assignments_page():
    """Serve the assignments listing page."""
    return render_template('assignments.html')

@app.route('/api/assignments')
@login_required
def get_assignments():
    """Get filtered and sorted assignments."""
    course_id = request.args.get('courseId')
    status = request.args.get('status')
    sort_by = request.args.get('sortBy', 'dueDate')

    cursor = mydb.cursor(dictionary=True)
    try:
        # Build the query based on filters
        query = """
            SELECT a.*, c.CourseName, 
                   COALESCE(s.Status, 'pending') as Status
            FROM Assignment a
            JOIN Course c ON a.CourseID = c.CourseID
            LEFT JOIN Submission s ON a.AssignmentID = s.AssignmentID 
                AND s.StudentID = %s
            WHERE 1=1
        """
        params = [session['user_id']]

        if course_id:
            query += " AND a.CourseID = %s"
            params.append(course_id)
        
        if status:
            query += " AND COALESCE(s.Status, 'pending') = %s"
            params.append(status)

        # Add sorting
        if sort_by == 'dueDate':
            query += " ORDER BY a.DueDate"
        elif sort_by == 'title':
            query += " ORDER BY a.Title"
        elif sort_by == 'status':
            query += " ORDER BY COALESCE(s.Status, 'pending')"

        cursor.execute(query, tuple(params))
        assignments = cursor.fetchall()

        return jsonify({'assignments': assignments}), 200
    except mysql.connector.Error as err:
        print(f"Error fetching assignments: {err}")
        return jsonify({'message': 'Failed to fetch assignments'}), 500

@app.route('/student/courses/exit/<int:course_id>', methods=['POST'])
@login_required
def exit_course(course_id):
    """Handle student's request to exit a course."""
    if session.get('role') != 'student':
        return jsonify({'success': False, 'message': 'Only students can exit courses'}), 403

    cursor = mydb.cursor(dictionary=True)
    try:
        # Start a transaction
        cursor.execute("START TRANSACTION")
        
        # Check if student is enrolled in the course
        cursor.execute("""
            SELECT 1 FROM Enrollment 
            WHERE StudentID = %s AND CourseID = %s AND Status = 'active'
        """, (session['user_id'], course_id))
        
        if not cursor.fetchone():
            cursor.execute("ROLLBACK")
            return jsonify({
                'success': False,
                'message': 'You are not enrolled in this course'
            }), 404

        # Delete the enrollment record instead of updating status
        cursor.execute("""
            DELETE FROM Enrollment 
            WHERE StudentID = %s AND CourseID = %s
        """, (session['user_id'], course_id))
        
        # Also delete any pending enrollment requests
        cursor.execute("""
            DELETE FROM EnrollmentRequest 
            WHERE StudentID = %s AND CourseID = %s
        """, (session['user_id'], course_id))
        
        cursor.execute("COMMIT")
        return jsonify({
            'success': True,
            'message': 'Successfully exited from the course'
        }), 200

    except mysql.connector.Error as err:
        cursor.execute("ROLLBACK")
        print(f"Error exiting course: {err}")
        return jsonify({
            'success': False,
            'message': 'Failed to exit course'
        }), 500

@app.route('/admin/enrollment/<action>/<int:request_id>', methods=['POST'])
@login_required
def handle_enrollment(action, request_id):
    if session.get('role') != 'admin':
        return jsonify({'success': False, 'message': 'Only admins can process enrollments'}), 403

    cursor = mydb.cursor()
    try:
        # Initialize OUT parameters
        cursor.execute("SET @success = 0")
        cursor.execute("SET @message = ''")
        
        # Call the stored procedure with OUT parameters
        cursor.execute(f"""
            CALL ProcessEnrollmentRequest(
                {request_id}, 
                {session['user_id']}, 
                '{action}', 
                @success, 
                @message
            )
        """)
        
        # Get the OUT parameter values
        cursor.execute("SELECT @success, @message")
        success, message = cursor.fetchone()
        
        mydb.commit()
        
        return jsonify({
            'success': bool(success),
            'message': message or f'Enrollment request {action}ed successfully'
        }), 200

    except mysql.connector.Error as err:
        print(f"Error processing enrollment: {err}")
        return jsonify({
            'success': False,
            'message': f'Database error: {str(err)}'
        }), 500
    finally:
        cursor.close()

# Notify clients when a dashboard update occurs
@socketio.on('connect')
def handle_connect():
    print('Client connected')

@socketio.on('disconnect')
def handle_disconnect():
    print('Client disconnected')

# Emit updates to the dashboard
@app.route('/trigger-dashboard-update', methods=['POST'])
@login_required
def trigger_dashboard_update():
    if session.get('role') == 'admin':
        socketio.emit('update_dashboard', {'message': 'Dashboard updated'}, broadcast=True)
        return jsonify({'success': True, 'message': 'Dashboard update triggered'}), 200
    return jsonify({'success': False, 'message': 'Unauthorized'}), 403

@app.route('/visualizations')
@login_required
def visualizations_page():
    """Serve the visualizations dashboard page with Grafana integration."""
    # Only admin can access the visualization dashboard
    if session.get('role') != 'admin':
        return redirect(url_for('index'))
    
    # Set Grafana URL based on environment (Docker or local)
    grafana_url = "http://localhost:3000"
    
    return render_template('visualizations.html', 
                           grafana_url=grafana_url,
                           user_role='admin')

if __name__ == '__main__':
    try:
        socketio.run(app, debug=True)
    except Exception as e:
        print(f"Application failed to start: {e}")
        exit(1)