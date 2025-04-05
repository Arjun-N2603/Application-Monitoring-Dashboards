-- Active: 1743599055481@@127.0.0.1@3306@practice
/*
University Assignment Portal - Database Schema

This script creates the database schema for the assignment portal with the following components:
1. User Management (User table with role-based access)
2. Course Management (Course, Enrollment, EnrollmentRequest tables)
3. Assignment Management (Assignment, Submission tables)
4. Content Management (CourseMaterial, Announcement tables)
5. Notification System (Notification table)

All tables include appropriate foreign key constraints and indexes for optimization.
*/

-- User table
CREATE TABLE User (
    UserID INT AUTO_INCREMENT PRIMARY KEY,
    Username VARCHAR(255) UNIQUE NOT NULL,
    Password VARCHAR(255) NOT NULL,  -- Store hashed passwords here
    FirstName VARCHAR(255),
    LastName VARCHAR(255),
    Email VARCHAR(255),
    Role ENUM('student', 'professor', 'admin') NOT NULL,
    Active BOOLEAN DEFAULT TRUE  -- Add this line
);

-- Course table
CREATE TABLE Course (
    CourseID INT AUTO_INCREMENT PRIMARY KEY,
    CourseName VARCHAR(255) NOT NULL,
    InstructorID INT,
    Year INT, 
    Semester INT,
    FOREIGN KEY (InstructorID) REFERENCES User(UserID)
);

-- Assignment table
CREATE TABLE Assignment (
    AssignmentID INT AUTO_INCREMENT PRIMARY KEY,
    CourseID INT NOT NULL,
    Title VARCHAR(255) NOT NULL,
    Description TEXT,
    DueDate DATETIME,
    MaxPoints INT NOT NULL,  -- Add this column to store maximum points for the assignment
    FOREIGN KEY (CourseID) REFERENCES Course(CourseID)
);

-- Defines relationship table (between User and Assignment)
CREATE TABLE Defines (
    UserID INT,
    AssignmentID INT,
    PRIMARY KEY (UserID, AssignmentID),  -- Composite primary key
    FOREIGN KEY (UserID) REFERENCES User(UserID),
    FOREIGN KEY (AssignmentID) REFERENCES Assignment(AssignmentID)
);

-- Announcement table
CREATE TABLE Announcement (
    AnnouncementID INT AUTO_INCREMENT PRIMARY KEY,
    Message TEXT,
    Timestamp DATETIME
);


-- Has relationship table (between Course and Announcement)
CREATE TABLE Has (
    CourseID INT,
    AnnouncementID INT,
    PRIMARY KEY (CourseID, AnnouncementID),  -- Composite primary key
    FOREIGN KEY (CourseID) REFERENCES Course(CourseID),
    FOREIGN KEY (AnnouncementID) REFERENCES Announcement(AnnouncementID)  -- Assuming you have an Announcement table
);

-- Modify Submission table to fix the column names and add necessary fields
DROP TABLE IF EXISTS Submission;
CREATE TABLE Submission (
    SubmissionID INT AUTO_INCREMENT PRIMARY KEY,
    AssignmentID INT NOT NULL,
    StudentID INT NOT NULL,
    SubmissionDate DATETIME DEFAULT CURRENT_TIMESTAMP,
    SubmissionPath VARCHAR(255) NOT NULL,  -- Added this field
    FileType VARCHAR(10),
    FileSize INT,
    Feedback TEXT,
    Grade VARCHAR(5),
    FOREIGN KEY (AssignmentID) REFERENCES Assignment(AssignmentID),
    FOREIGN KEY (StudentID) REFERENCES User(UserID)
);

-- Update Submission table to include grading fields
ALTER TABLE Submission
ADD COLUMN GradedDate DATETIME NULL;

-- Add index for faster grading queries
CREATE INDEX idx_submission_assignment ON Submission(AssignmentID);

-- GradeRubric table (linked to Assignment)
CREATE TABLE GradeRubric (
    RubricID INT AUTO_INCREMENT PRIMARY KEY,
    AssignmentID INT NOT NULL,
    Criteria TEXT, 
    Points INT,
    FOREIGN KEY (AssignmentID) REFERENCES Assignment(AssignmentID)
);

-- Notification table
CREATE TABLE Notification (
    NotificationID INT AUTO_INCREMENT PRIMARY KEY,
    UserID INT NOT NULL,
    Message TEXT,
    Timestamp DATETIME,
    Status ENUM('read', 'unread') DEFAULT 'unread',
    FOREIGN KEY (UserID) REFERENCES User(UserID)
);

-- Course Material table
CREATE TABLE IF NOT EXISTS CourseMaterial (
    MaterialID INT AUTO_INCREMENT PRIMARY KEY,
    CourseID INT NOT NULL,
    FilePath VARCHAR(255) NOT NULL,
    Description TEXT,
    UploadDate DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (CourseID) REFERENCES Course(CourseID) ON DELETE CASCADE
);

-- Enrollment table
CREATE TABLE Enrollment (
    EnrollmentID INT AUTO_INCREMENT PRIMARY KEY,
    StudentID INT NOT NULL,
    CourseID INT NOT NULL,
    EnrollmentDate DATETIME DEFAULT CURRENT_TIMESTAMP,
    Status ENUM('active', 'dropped') DEFAULT 'active',
    FOREIGN KEY (StudentID) REFERENCES User(UserID),
    FOREIGN KEY (CourseID) REFERENCES Course(CourseID),
    UNIQUE KEY unique_enrollment (StudentID, CourseID)
);

CREATE TABLE EnrollmentRequest (
    RequestID INT AUTO_INCREMENT PRIMARY KEY,
    StudentID INT NOT NULL,
    CourseID INT NOT NULL,
    RequestDate DATETIME DEFAULT CURRENT_TIMESTAMP,
    ProcessedDate DATETIME,
    Status ENUM('pending', 'approved', 'rejected') DEFAULT 'pending',
    FOREIGN KEY (StudentID) REFERENCES User(UserID),
    FOREIGN KEY (CourseID) REFERENCES Course(CourseID),
    UNIQUE KEY unique_request (StudentID, CourseID, Status)
);

