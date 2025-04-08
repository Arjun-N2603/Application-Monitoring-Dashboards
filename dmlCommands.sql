-- Active: 1743599055481@@127.0.0.1@3306@university_assignment_portal
-- ==========================================
-- User Authentication Queries
-- ==========================================

-- Register new user
INSERT INTO User (Username, Password, FirstName, LastName, Email, Role) 
VALUES (%s, %s, %s, %s, %s, %s);


INSERT INTO User (Username, Password, FirstName, LastName, Email, Role) 
VALUES ('admin', 'admin', 'admin', 'admin', 'admin', 'admin');

-- Login validation
SELECT * FROM User WHERE Username = %s;

-- ==========================================
-- Admin Dashboard Queries
-- ==========================================

-- Get dashboard statistics
SELECT 
    (SELECT COUNT(*) FROM User WHERE Role = 'student' AND Active = 1) as student_count,
    (SELECT COUNT(*) FROM User WHERE Role = 'professor' AND Active = 1) as professor_count,
    (SELECT COUNT(*) FROM Course) as active_courses,
    (SELECT COUNT(*) FROM Assignment 
     WHERE DueDate > CURRENT_TIMESTAMP 
     AND Status = 'active') as active_assignments;

-- Get courses with enrollment counts
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
ORDER BY c.CourseCode;

-- Get pending enrollment requests
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
WHERE er.Status = 'pending'
ORDER BY er.RequestDate DESC;

-- Get active professors
SELECT UserID, FirstName, LastName, Email 
FROM User 
WHERE Role = 'professor' AND Active = 1
ORDER BY FirstName, LastName;

-- ==========================================
-- Course Management Queries
-- ==========================================

-- Create new course
INSERT INTO Course (CourseName, CourseCode, InstructorID, Year, Semester) 
VALUES (%s, %s, %s, %s, %s);

-- Verify professor status
SELECT UserID, Role 
FROM User 
WHERE UserID = %s AND Role = 'professor' AND Active = 1;

-- Update course details
UPDATE Course 
SET CourseName = %s, 
    CourseCode = %s, 
    InstructorID = %s, 
    Year = %s, 
    Semester = %s
WHERE CourseID = %s;

-- Delete course and related data (within transaction)
DELETE FROM Enrollment WHERE CourseID = %s;
DELETE FROM EnrollmentRequest WHERE CourseID = %s;
DELETE s FROM Submission s
INNER JOIN Assignment a ON s.AssignmentID = a.AssignmentID
WHERE a.CourseID = %s;
DELETE FROM Assignment WHERE CourseID = %s;
DELETE FROM Course WHERE CourseID = %s;

-- ==========================================
-- Assignment Management Queries
-- ==========================================

-- Create new assignment
INSERT INTO Assignment (CourseID, Title, Description, DueDate, FilePath, CreatedBy, CreatedAt)
VALUES (%s, %s, %s, %s, %s, %s, NOW());

-- Create notifications for new assignment
INSERT INTO Notification (UserID, Message, Timestamp)
SELECT e.StudentID, 
       CONCAT('New assignment posted in ', c.CourseName, ': ', %s),
       NOW()
FROM Enrollment e
JOIN Course c ON e.CourseID = c.CourseID
WHERE e.CourseID = %s AND e.Status = 'active';

-- Get assignments for a course
SELECT 
    AssignmentID as id,
    Title as title,
    DueDate as due_date,
    (SELECT COUNT(*) FROM Submission s WHERE s.AssignmentID = a.AssignmentID) as submission_count,
    (SELECT COUNT(*) FROM Enrollment e WHERE e.CourseID = a.CourseID) as total_students
FROM Assignment a
WHERE CourseID = %s
ORDER BY DueDate DESC;

-- ==========================================
-- Submission Management Queries
-- ==========================================

-- Record new submission
INSERT INTO Submission 
(AssignmentID, StudentID, SubmissionPath, SubmissionDate) 
VALUES (%s, %s, %s, NOW())
ON DUPLICATE KEY UPDATE 
SubmissionPath = VALUES(SubmissionPath),
SubmissionDate = NOW();

-- Get submission details
SELECT s.SubmissionPath, s.AssignmentID
FROM Submission s
JOIN Assignment a ON s.AssignmentID = a.AssignmentID
JOIN Course c ON a.CourseID = c.CourseID
WHERE s.SubmissionID = %s AND c.InstructorID = %s;

-- ==========================================
-- Enrollment Management Queries
-- ==========================================

-- Check existing enrollment request
SELECT 1 FROM EnrollmentRequest 
WHERE StudentID = %s AND CourseID = %s AND Status = 'pending';

-- Create enrollment request
INSERT INTO EnrollmentRequest (StudentID, CourseID, RequestDate, Status)
VALUES (%s, %s, NOW(), 'pending');

-- Process enrollment request (approve/reject)
UPDATE EnrollmentRequest 
SET Status = 'rejected', ProcessedDate = NOW() 
WHERE RequestID = %s AND Status = 'pending';

-- Exit course (student)
DELETE FROM Enrollment 
WHERE StudentID = %s AND CourseID = %s;

DELETE FROM EnrollmentRequest 
WHERE StudentID = %s AND CourseID = %s;

-- ==========================================
-- Course Material Management Queries
-- ==========================================

-- Add course material
INSERT INTO CourseMaterial (CourseID, FilePath, Description, UploadDate)
VALUES (%s, %s, %s, NOW());

-- ==========================================
-- Course Details Queries
-- ==========================================

-- Get detailed course information
SELECT c.*, 
       u.FirstName, u.LastName,
       COUNT(DISTINCT e.StudentID) as enrolled_count
FROM Course c
JOIN User u ON c.InstructorID = u.UserID
LEFT JOIN Enrollment e ON c.CourseID = e.CourseID
WHERE c.CourseID = %s
GROUP BY c.CourseID;

-- Get student progress in course
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
GROUP BY u.UserID, u.FirstName, u.LastName;
