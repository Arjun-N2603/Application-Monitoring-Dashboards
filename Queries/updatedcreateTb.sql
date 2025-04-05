-- Active: 1743599055481@@127.0.0.1@3306@university_assignment_portal
CREATE TABLE user (
    UserID int NOT NULL AUTO_INCREMENT,
    Username varchar(255) NOT NULL,
    Password varchar(255) NOT NULL,
    FirstName varchar(255) DEFAULT NULL,
    LastName varchar(255) DEFAULT NULL,
    Email varchar(255) DEFAULT NULL,
    Role enum(
        'student',
        'professor',
        'admin'
    ) NOT NULL,
    CreatedAt datetime DEFAULT CURRENT_TIMESTAMP,
    Active tinyint(1) DEFAULT '1',
    LastLogin datetime DEFAULT NULL,
    PRIMARY KEY (UserID),
    UNIQUE KEY Username (Username)
) ENGINE = InnoDB AUTO_INCREMENT = 30 DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci;

CREATE TABLE course (
    CourseID int NOT NULL AUTO_INCREMENT,
    CourseName varchar(255) NOT NULL,
    CourseCode varchar(10) NOT NULL,
    InstructorID int DEFAULT NULL,
    Year int DEFAULT NULL,
    Semester int DEFAULT NULL,
    CreatedAt datetime DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (CourseID),
    KEY course_instructor_fk (InstructorID),
    CONSTRAINT course_ibfk_1 FOREIGN KEY (InstructorID) REFERENCES user (UserID),
    CONSTRAINT course_instructor_fk FOREIGN KEY (InstructorID) REFERENCES user (UserID) ON DELETE SET NULL
) ENGINE = InnoDB AUTO_INCREMENT = 7 DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci;

CREATE TABLE assignment (
    AssignmentID int NOT NULL AUTO_INCREMENT,
    CourseID int NOT NULL,
    Title varchar(255) NOT NULL,
    Description text,
    DueDate datetime DEFAULT NULL,
    Status varchar(20) DEFAULT 'active',
    MaxPoints int DEFAULT '100',
    FilePath varchar(2048) DEFAULT NULL,
    CreatedBy int DEFAULT NULL,
    CreatedAt datetime DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (AssignmentID),
    KEY CreatedBy (CreatedBy),
    KEY assignment_course_fk (CourseID),
    CONSTRAINT assignment_course_fk FOREIGN KEY (CourseID) REFERENCES course (CourseID) ON DELETE CASCADE,
    CONSTRAINT assignment_ibfk_1 FOREIGN KEY (CourseID) REFERENCES course (CourseID),
    CONSTRAINT assignment_ibfk_2 FOREIGN KEY (CreatedBy) REFERENCES user (UserID)
) ENGINE = InnoDB AUTO_INCREMENT = 11 DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci;

CREATE TABLE defines (
    UserID int NOT NULL,
    AssignmentID int NOT NULL,
    PRIMARY KEY (UserID, AssignmentID),
    KEY AssignmentID (AssignmentID),
    CONSTRAINT defines_ibfk_1 FOREIGN KEY (UserID) REFERENCES user (UserID),
    CONSTRAINT defines_ibfk_2 FOREIGN KEY (AssignmentID) REFERENCES assignment (AssignmentID)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci;

CREATE TABLE announcement (
    AnnouncementID int NOT NULL AUTO_INCREMENT,
    Message text,
    Timestamp datetime DEFAULT NULL,
    PRIMARY KEY (AnnouncementID)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci;

CREATE TABLE has (
    CourseID int NOT NULL,
    AnnouncementID int NOT NULL,
    PRIMARY KEY (CourseID, AnnouncementID),
    KEY AnnouncementID (AnnouncementID),
    CONSTRAINT has_ibfk_1 FOREIGN KEY (CourseID) REFERENCES course (CourseID),
    CONSTRAINT has_ibfk_2 FOREIGN KEY (AnnouncementID) REFERENCES announcement (AnnouncementID)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci;

CREATE TABLE submission (
    SubmissionID int NOT NULL AUTO_INCREMENT,
    AssignmentID int NOT NULL,
    StudentID int NOT NULL,
    SubmissionDate datetime DEFAULT CURRENT_TIMESTAMP,
    SubmissionPath varchar(2048) DEFAULT NULL,
    FileType varchar(10) DEFAULT NULL,
    FileSize int DEFAULT NULL,
    Feedback text,
    Grade varchar(5) DEFAULT NULL,
    GradedDate datetime DEFAULT NULL,
    LastModified datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    Points int DEFAULT NULL,
    Comments text,
    GradedAt datetime DEFAULT NULL,
    GradedBy int DEFAULT NULL,
    PRIMARY KEY (SubmissionID),
    KEY StudentID (StudentID),
    KEY idx_submission_assignment (AssignmentID),
    KEY GradedBy (GradedBy),
    KEY idx_submission_grading (
        AssignmentID,
        StudentID,
        Points
    ),
    CONSTRAINT submission_ibfk_1 FOREIGN KEY (AssignmentID) REFERENCES assignment (AssignmentID),
    CONSTRAINT submission_ibfk_2 FOREIGN KEY (StudentID) REFERENCES user (UserID),
    CONSTRAINT submission_ibfk_3 FOREIGN KEY (GradedBy) REFERENCES user (UserID)
) ENGINE = InnoDB AUTO_INCREMENT = 8 DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci;

CREATE TABLE graderubric (
    RubricID int NOT NULL AUTO_INCREMENT,
    AssignmentID int NOT NULL,
    Criteria text,
    Points int DEFAULT NULL,
    PRIMARY KEY (RubricID),
    KEY AssignmentID (AssignmentID),
    CONSTRAINT graderubric_ibfk_1 FOREIGN KEY (AssignmentID) REFERENCES assignment (AssignmentID)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci;

CREATE TABLE notification (
    NotificationID int NOT NULL AUTO_INCREMENT,
    UserID int NOT NULL,
    Message text,
    Timestamp datetime DEFAULT NULL,
    Status enum('read', 'unread') DEFAULT 'unread',
    PRIMARY KEY (NotificationID),
    KEY UserID (UserID),
    CONSTRAINT notification_ibfk_1 FOREIGN KEY (UserID) REFERENCES user (UserID)
) ENGINE = InnoDB AUTO_INCREMENT = 42 DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci;

CREATE TABLE coursematerial (
    MaterialID int NOT NULL AUTO_INCREMENT,
    CourseID int NOT NULL,
    FilePath varchar(2048) DEFAULT NULL,
    Description text,
    UploadDate datetime DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (MaterialID),
    KEY CourseID (CourseID),
    CONSTRAINT coursematerial_ibfk_1 FOREIGN KEY (CourseID) REFERENCES course (CourseID) ON DELETE CASCADE
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci;

CREATE TABLE enrollment (
    EnrollmentID int NOT NULL AUTO_INCREMENT,
    StudentID int NOT NULL,
    CourseID int NOT NULL,
    EnrollmentDate datetime DEFAULT CURRENT_TIMESTAMP,
    Status enum('active', 'dropped') DEFAULT 'active',
    PRIMARY KEY (EnrollmentID),
    UNIQUE KEY unique_enrollment (StudentID, CourseID),
    KEY enrollment_course_fk (CourseID),
    CONSTRAINT enrollment_course_fk FOREIGN KEY (CourseID) REFERENCES course (CourseID) ON DELETE CASCADE,
    CONSTRAINT enrollment_ibfk_1 FOREIGN KEY (StudentID) REFERENCES user (UserID),
    CONSTRAINT enrollment_ibfk_2 FOREIGN KEY (CourseID) REFERENCES course (CourseID)
) ENGINE = InnoDB AUTO_INCREMENT = 18 DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci;

CREATE TABLE enrollmentrequest (
    RequestID int NOT NULL AUTO_INCREMENT,
    StudentID int NOT NULL,
    CourseID int NOT NULL,
    RequestDate datetime DEFAULT CURRENT_TIMESTAMP,
    ProcessedDate datetime DEFAULT NULL,
    Status enum(
        'pending',
        'approved',
        'rejected'
    ) DEFAULT 'pending',
    PRIMARY KEY (RequestID),
    UNIQUE KEY unique_request (
        StudentID,
        CourseID,
        Status
    ),
    KEY enrollment_request_course_fk (CourseID),
    CONSTRAINT enrollment_request_course_fk FOREIGN KEY (CourseID) REFERENCES course (CourseID) ON DELETE CASCADE,
    CONSTRAINT enrollmentrequest_ibfk_1 FOREIGN KEY (StudentID) REFERENCES user (UserID),
    CONSTRAINT enrollmentrequest_ibfk_2 FOREIGN KEY (CourseID) REFERENCES course (CourseID)
) ENGINE = InnoDB AUTO_INCREMENT = 20 DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci;