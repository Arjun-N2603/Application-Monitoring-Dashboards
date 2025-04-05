-- Active: 1743599055481@@127.0.0.1@3306@university_assignment_portal
DELIMITER //

/*
University Assignment Portal - Database Triggers

This script defines triggers that enforce business rules and maintain data integrity:
1. Role-based Access Control
2. Submission Deadlines
3. Grade Management
4. Course Material Management
5. Enrollment Processing

Each trigger includes proper error handling and user notification.
*/

-- Clean up existing triggers
DROP TRIGGER IF EXISTS before_course_material_insert//
DROP TRIGGER IF EXISTS before_submission_insert//
DROP TRIGGER IF EXISTS before_enrollment_insert//
DROP TRIGGER IF EXISTS before_course_insert//
DROP TRIGGER IF EXISTS before_assignment_insert//
DROP TRIGGER IF EXISTS before_course_material_update//
DROP TRIGGER IF EXISTS before_assignment_update//

-- Create course material trigger
CREATE TRIGGER before_course_material_insert
BEFORE INSERT ON CourseMaterial
FOR EACH ROW
BEGIN
    DECLARE user_role VARCHAR(20);
    
    -- Get the role using the session variable
    SELECT Role INTO user_role
    FROM User
    WHERE UserID = @current_user_id;
    
    IF user_role != 'professor' THEN
        SIGNAL SQLSTATE '45000'
        SET MESSAGE_TEXT = 'Only professors can upload course materials';
    END IF;
    
    -- Also verify if professor teaches this course
    IF NOT EXISTS (
        SELECT 1
        FROM Course
        WHERE CourseID = NEW.CourseID 
        AND InstructorID = @current_user_id
    ) THEN
        SIGNAL SQLSTATE '45000'
        SET MESSAGE_TEXT = 'You can only upload materials to courses you teach';
    END IF;
END//

-- Create submission trigger
CREATE TRIGGER before_submission_insert
BEFORE INSERT ON Submission
FOR EACH ROW
BEGIN
    DECLARE user_role VARCHAR(20);
    
    -- Get the role of the user trying to submit
    SELECT Role INTO user_role
    FROM User
    WHERE UserID = NEW.StudentID;
    
    IF user_role != 'student' THEN
        SIGNAL SQLSTATE '45000'
        SET MESSAGE_TEXT = 'Only students can submit assignments';
    END IF;
END//

-- Create enrollment trigger
CREATE TRIGGER before_enrollment_insert
BEFORE INSERT ON Enrollment
FOR EACH ROW
BEGIN
    IF EXISTS (
        SELECT 1 FROM Enrollment 
        WHERE StudentID = NEW.StudentID 
        AND CourseID = NEW.CourseID 
        AND Status = 'active'
    ) THEN
        SIGNAL SQLSTATE '45000'
        SET MESSAGE_TEXT = 'Student is already enrolled in this course';
    END IF;
END//

-- Create course creation trigger
CREATE TRIGGER before_course_insert
BEFORE INSERT ON Course
FOR EACH ROW
BEGIN
    DECLARE creator_role VARCHAR(20);
    SELECT Role INTO creator_role FROM User WHERE UserID = @current_user_id;
    
    IF creator_role != 'admin' THEN
        SIGNAL SQLSTATE '45000'
        SET MESSAGE_TEXT = 'Only administrators can create courses';
    END IF;
END//

-- Create assignment trigger
CREATE TRIGGER before_assignment_insert
BEFORE INSERT ON Assignment
FOR EACH ROW
BEGIN
    IF NEW.DueDate <= NOW() THEN
        SIGNAL SQLSTATE '45000'
        SET MESSAGE_TEXT = 'Due date must be in the future';
    END IF;
END//

-- Create course material update trigger
CREATE TRIGGER before_course_material_update
BEFORE UPDATE ON CourseMaterial
FOR EACH ROW
BEGIN
    DECLARE user_role VARCHAR(20);
    
    SELECT Role INTO user_role
    FROM User
    WHERE UserID = @current_user_id;
    
    IF user_role != 'professor' THEN
        SIGNAL SQLSTATE '45000'
        SET MESSAGE_TEXT = 'Only professors can modify course materials';
    END IF;
    
    IF NOT EXISTS (
        SELECT 1
        FROM Course
        WHERE CourseID = NEW.CourseID 
        AND InstructorID = @current_user_id
    ) THEN
        SIGNAL SQLSTATE '45000'
        SET MESSAGE_TEXT = 'You can only modify materials in courses you teach';
    END IF;
END//

-- Create assignment update trigger
CREATE TRIGGER before_assignment_update
BEFORE UPDATE ON Assignment
FOR EACH ROW
BEGIN
    IF NEW.DueDate <= NOW() AND OLD.DueDate != NEW.DueDate THEN
        SIGNAL SQLSTATE '45000'
        SET MESSAGE_TEXT = 'Cannot update due date to a past date';
    END IF;
END//

-- Trigger for validating grades
CREATE TRIGGER before_grade_update
BEFORE UPDATE ON Submission
FOR EACH ROW
BEGIN
    DECLARE user_role VARCHAR(20);
    
    -- Get the role of the user trying to grade
    SELECT Role INTO user_role
    FROM User
    WHERE UserID = @current_user_id;
    
    -- Only professors can grade submissions
    IF user_role != 'professor' THEN
        SIGNAL SQLSTATE '45000'
        SET MESSAGE_TEXT = 'Only professors can grade submissions';
    END IF;
    
    -- Validate grade format (assuming grades are like A, B, C, D, F or numeric 0-100)
    IF NEW.Grade IS NOT NULL AND NEW.Grade NOT REGEXP '^([A-F]|[0-9]|[1-9][0-9]|100)$' THEN
        SIGNAL SQLSTATE '45000'
        SET MESSAGE_TEXT = 'Invalid grade format';
    END IF;
END//

-- Trigger for preventing grade modifications after a certain period
CREATE TRIGGER before_grade_modification
BEFORE UPDATE ON Submission
FOR EACH ROW
BEGIN
    DECLARE grade_lock_period INT DEFAULT 48; -- hours
    
    IF OLD.Grade IS NOT NULL 
       AND OLD.GradedDate IS NOT NULL 
       AND TIMESTAMPDIFF(HOUR, OLD.GradedDate, NOW()) > grade_lock_period THEN
        SIGNAL SQLSTATE '45000'
        SET MESSAGE_TEXT = 'Grades cannot be modified after 48 hours of initial grading';
    END IF;
END//

-- Trigger for notifying students when grades are posted
CREATE TRIGGER after_grade_insert
AFTER UPDATE ON Submission
FOR EACH ROW
BEGIN
    IF NEW.Grade IS NOT NULL AND (OLD.Grade IS NULL OR NEW.Grade != OLD.Grade) THEN
        INSERT INTO Notification (UserID, Message, Timestamp)
        SELECT 
            NEW.StudentID,
            CONCAT('Your grade for assignment has been posted: ', NEW.Grade),
            NOW();
    END IF;
END//

-- Trigger for assignment deadline enforcement
CREATE TRIGGER before_submission_deadline
BEFORE INSERT ON Submission
FOR EACH ROW
BEGIN
    DECLARE deadline DATETIME;
    
    -- Get assignment deadline
    SELECT DueDate INTO deadline
    FROM Assignment
    WHERE AssignmentID = NEW.AssignmentID;
    
    -- Check if submission is past deadline
    IF NOW() > deadline THEN
        SIGNAL SQLSTATE '45000'
        SET MESSAGE_TEXT = 'Cannot submit assignment after deadline';
    END IF;
END//

DELIMITER ;