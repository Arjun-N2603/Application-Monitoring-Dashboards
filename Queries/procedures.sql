-- Active: 1743599055481@@127.0.0.1@3306@university_assignment_portal
DELIMITER //
-- Clean up existing procedures
DROP PROCEDURE IF EXISTS GetProfessorDashboard//
DROP PROCEDURE IF EXISTS GetStudentDashboard//
DROP PROCEDURE IF EXISTS GetCourseDetails//
DROP PROCEDURE IF EXISTS GradeSubmission//
DROP PROCEDURE IF EXISTS ProcessEnrollmentRequest//

-- Professor Dashboard Data Procedure
CREATE PROCEDURE GetProfessorDashboard(IN professor_id INT)
BEGIN
    -- Get professor stats
    SELECT 
        (SELECT COUNT(*) FROM Course 
         WHERE InstructorID = professor_id) as active_courses,
        (SELECT COUNT(DISTINCT e.StudentID) 
         FROM Enrollment e 
         JOIN Course c ON e.CourseID = c.CourseID 
         WHERE c.InstructorID = professor_id) as total_students,
        (SELECT COUNT(*) FROM Submission s 
         JOIN Assignment a ON s.AssignmentID = a.AssignmentID 
         JOIN Course c ON a.CourseID = c.CourseID 
         WHERE c.InstructorID = professor_id AND s.Grade IS NULL) as pending_assignments;
    
    -- Get teaching courses with detailed information
    SELECT 
        c.*,
        (SELECT COUNT(DISTINCT e.StudentID) 
         FROM Enrollment e 
         WHERE e.CourseID = c.CourseID) as enrolled_students,
        (SELECT COUNT(a.AssignmentID) 
         FROM Assignment a 
         WHERE a.CourseID = c.CourseID) as assignment_count,
        (SELECT COUNT(*) 
         FROM Submission s 
         JOIN Assignment a ON s.AssignmentID = a.AssignmentID 
         WHERE a.CourseID = c.CourseID AND s.Grade IS NULL) as pending_submissions
    FROM Course c
    WHERE c.InstructorID = professor_id
    ORDER BY c.Year DESC, c.Semester DESC;
    
    -- Get recent submissions
    SELECT 
        CONCAT(u.FirstName, ' ', u.LastName) as student_name,
        a.Title as assignment_title,
        c.CourseName as course_name,
        s.SubmissionDate,
        s.Grade,
        s.SubmissionID,
        a.MaxPoints
    FROM Submission s
    JOIN Assignment a ON s.AssignmentID = a.AssignmentID
    JOIN Course c ON a.CourseID = c.CourseID
    JOIN User u ON s.StudentID = u.UserID
    WHERE c.InstructorID = professor_id
    ORDER BY s.SubmissionDate DESC
    LIMIT 10;
END//

-- Student Dashboard Data Procedure
CREATE PROCEDURE GetStudentDashboard(IN student_id INT)
BEGIN
    -- Get enrolled and available courses
    SELECT c.*, 
           u.FirstName as instructor_name,
           CASE WHEN e.StudentID IS NOT NULL THEN TRUE ELSE FALSE END as is_enrolled
    FROM Course c
    JOIN User u ON c.InstructorID = u.UserID
    LEFT JOIN Enrollment e ON c.CourseID = e.CourseID AND e.StudentID = student_id;

    -- Get assignments for enrolled courses
    SELECT 
        a.AssignmentID,
        a.Title,
        a.Description,
        a.DueDate,
        a.FilePath,
        c.CourseName,
        c.CourseCode,
        COALESCE(s.SubmissionPath, NULL) as submission,
        COALESCE(s.Grade, NULL) as grade,
        CASE 
            WHEN s.SubmissionPath IS NOT NULL THEN 'submitted'
            WHEN a.DueDate < NOW() THEN 'late'
            ELSE 'pending'
        END as status
    FROM Assignment a
    JOIN Course c ON a.CourseID = c.CourseID
    JOIN Enrollment e ON c.CourseID = e.CourseID
    LEFT JOIN Submission s ON a.AssignmentID = s.AssignmentID 
        AND s.StudentID = student_id
    WHERE e.StudentID = student_id AND e.Status = 'active'
    ORDER BY a.DueDate ASC;
END//

-- Course Details Procedure
CREATE PROCEDURE GetCourseDetails(IN course_id INT, IN professor_id INT)
BEGIN
    -- Get basic course info
    SELECT c.*, 
           (SELECT COUNT(DISTINCT e.StudentID) 
            FROM Enrollment e 
            WHERE e.CourseID = c.CourseID) as enrolled_count,
           (SELECT COUNT(*) 
            FROM Assignment a 
            WHERE a.CourseID = c.CourseID 
            AND a.DueDate > NOW()) as active_assignments
    FROM Course c
    WHERE c.CourseID = course_id AND c.InstructorID = professor_id;

    -- Get enrolled students with progress
    SELECT 
        u.UserID,
        CONCAT(u.FirstName, ' ', u.LastName) as name,
        u.Email,
        (
            SELECT COUNT(DISTINCT s.SubmissionID)
            FROM Submission s
            JOIN Assignment a ON s.AssignmentID = a.AssignmentID
            WHERE s.StudentID = u.UserID 
            AND a.CourseID = course_id
        ) as completed_assignments,
        (
            SELECT COUNT(*)
            FROM Assignment
            WHERE CourseID = course_id
        ) as total_assignments,
        (
            SELECT AVG(CAST(s.Grade AS DECIMAL(5,2)))
            FROM Submission s
            JOIN Assignment a ON s.AssignmentID = a.AssignmentID
            WHERE s.StudentID = u.UserID 
            AND a.CourseID = course_id
            AND s.Grade IS NOT NULL
        ) as average_grade
    FROM User u
    JOIN Enrollment e ON u.UserID = e.StudentID
    WHERE e.CourseID = course_id AND e.Status = 'active'
    GROUP BY u.UserID, u.FirstName, u.LastName, u.Email;

    -- Get course assignments
    SELECT 
        a.AssignmentID as id,
        a.Title as title,
        a.DueDate as due_date,
        COUNT(DISTINCT s.StudentID) as submission_count,
        (SELECT COUNT(*) FROM Enrollment WHERE CourseID = course_id) as total_students
    FROM Assignment a
    LEFT JOIN Submission s ON a.AssignmentID = s.AssignmentID
    WHERE a.CourseID = course_id
    GROUP BY a.AssignmentID;
END//

-- Grade Submission Procedure
CREATE PROCEDURE GradeSubmission(
    IN submission_id INT,
    IN professor_id INT,
    IN grade_value INT,
    IN feedback_text TEXT,
    OUT success BOOLEAN,
    OUT message VARCHAR(255)
)
BEGIN
    DECLARE course_id INT;
    DECLARE max_points INT;
    DECLARE student_id INT;
    
    -- Start transaction
    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        SET success = FALSE;
        SET message = 'An error occurred while grading the submission';
    END;
    
    START TRANSACTION;
    
    -- Verify professor teaches this course
    SELECT c.CourseID, a.MaxPoints, s.StudentID 
    INTO course_id, max_points, student_id
    FROM Course c
    JOIN Assignment a ON c.CourseID = a.CourseID
    JOIN Submission s ON a.AssignmentID = s.AssignmentID
    WHERE s.SubmissionID = submission_id 
    AND c.InstructorID = professor_id;
    
    IF course_id IS NULL THEN
        SET success = FALSE;
        SET message = 'Not authorized to grade this submission';
        ROLLBACK;
    ELSEIF grade_value < 0 OR grade_value > max_points THEN
        SET success = FALSE;
        SET message = CONCAT('Grade must be between 0 and ', max_points);
        ROLLBACK;
    ELSE
        -- Update the submission
        UPDATE Submission 
        SET Grade = grade_value,
            Feedback = feedback_text,
            GradedDate = NOW()
        WHERE SubmissionID = submission_id;
        
        -- Create notification
        INSERT INTO Notification (UserID, Message, Timestamp)
        SELECT student_id, 
               CONCAT('Your submission has been graded with ', grade_value, ' points'),
               NOW();
               
        SET success = TRUE;
        SET message = 'Submission graded successfully';
        COMMIT;
    END IF;
END//

-- Process Enrollment Request Procedure
CREATE PROCEDURE ProcessEnrollmentRequest(
    IN request_id INT,
    IN admin_id INT,
    IN action VARCHAR(10),
    OUT success BOOLEAN,
    OUT message VARCHAR(255)
)
BEGIN
    DECLARE student_id INT;
    DECLARE course_id INT;
    DECLARE request_status VARCHAR(20);
    DECLARE is_enrolled BOOLEAN;
    
    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        SET success = FALSE;
        SET message = 'An error occurred while processing the request';
    END;
    
    START TRANSACTION;
    
    -- Get request details
    SELECT er.StudentID, er.CourseID, er.Status,
           EXISTS(SELECT 1 FROM Enrollment e 
                 WHERE e.StudentID = er.StudentID 
                 AND e.CourseID = er.CourseID) as already_enrolled
    INTO student_id, course_id, request_status, is_enrolled
    FROM EnrollmentRequest er
    WHERE er.RequestID = request_id;
    
    IF request_status IS NULL THEN
        SET success = FALSE;
        SET message = 'Enrollment request not found';
        ROLLBACK;
    ELSEIF request_status != 'pending' THEN
        SET success = FALSE;
        SET message = 'Request has already been processed';
        ROLLBACK;
    ELSEIF is_enrolled = TRUE THEN
        SET success = FALSE;
        SET message = 'Student is already enrolled in this course';
        ROLLBACK;
    ELSE
        IF action = 'approve' THEN
            -- Insert only if not already enrolled
            INSERT IGNORE INTO Enrollment (StudentID, CourseID, EnrollmentDate, Status)
            VALUES (student_id, course_id, NOW(), 'active');
            
            -- Update request status
            UPDATE EnrollmentRequest 
            SET Status = 'approved',
                ProcessedDate = NOW() 
            WHERE RequestID = request_id;
            
            -- Create notification
            INSERT INTO Notification (UserID, Message, Timestamp)
            SELECT student_id, 
                CONCAT('Your enrollment request for ', 
                    (SELECT CourseName FROM Course WHERE CourseID = course_id),
                    ' has been approved'),
                NOW();
                
        ELSEIF action = 'reject' THEN
            -- Update request status
            UPDATE EnrollmentRequest 
            SET Status = 'rejected',
                ProcessedDate = NOW() 
            WHERE RequestID = request_id;
            
            -- Create notification
            INSERT INTO Notification (UserID, Message, Timestamp)
            SELECT student_id, 
                CONCAT('Your enrollment request for ',
                    (SELECT CourseName FROM Course WHERE CourseID = course_id),
                    ' has been rejected'),
                NOW();
        END IF;
        
        SET success = TRUE;
        SET message = CONCAT('Enrollment request ', action, 'd successfully');
        COMMIT;
    END IF;
END//

DELIMITER ;
