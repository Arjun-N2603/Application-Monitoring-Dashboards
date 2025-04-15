import requests
import time
import random
import threading
import logging
import argparse

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class APILoadGenerator:
    """Generate load for API testing by simulating user activity."""

    def __init__(self, base_url="http://localhost:5000", users=5, request_interval=1):
        self.base_url = base_url
        self.users = users  # Number of concurrent users
        self.request_interval = request_interval  # Time between requests in seconds
        self.running = False
        # Define user credentials for each role
        self.user_credentials = [
            {"username": "admin2", "password": "admin2", "role": "admin"},
            {"username": "prof", "password": "prof", "role": "professor"},
            {"username": "student", "password": "student", "role": "student"}
        ]
        # Define endpoints accessible by each role - MODIFIED FOR DASHBOARDS
        self.role_endpoints = {
            "admin": [
                {"path": "/admin-dashboard", "method": "GET"},
                {"path": "/api/professors", "method": "GET"},
                {"path": "/admin-dashboard-page", "method": "GET"},
                {"path": "/admin/courses/create", "method": "POST"}, # Example admin action
                {"path": "/admin/enrollment/approve/1", "method": "POST"} # Example admin action - adjust request_id
            ],
            "professor": [
                {"path": "/professor-dashboard", "method": "GET"},
                {"path": "/professor-dashboard-page", "method": "GET"},
                {"path": "/api/courses/1/details", "method": "GET"}, # Example course details
                {"path": "/courses/1/assignments", "method": "POST", "data": {"title": "Test Assignment", "due_date": "2024-12-31 23:59:59"}}, # Create assignment - adjust course_id and data
                {"path": "/assignments/1/submissions", "method": "GET"}, # Get submissions - adjust assignment_id
                {"path": "/submissions/1/grade", "method": "POST", "data": {"grade": 85, "feedback": "Good work!"}}, # Grade submission - adjust submission_id and data
                {"path": "/api/assignments/upload", "method": "POST"} # Upload assignment file - would need to handle file upload in load generator if needed
            ],
            "student": [
                {"path": "/student-dashboard", "method": "GET"},
                {"path": "/student-dashboard-page", "method": "GET"},
                {"path": "/api/assignments", "method": "GET"}, # Get assignments list
                {"path": "/assignments/1/submit", "method": "POST"}, # Submit assignment - adjust assignment_id - would need to handle file upload
                {"path": "/student/courses/request/1", "method": "POST"}, # Request enrollment - adjust course_id
                {"path": "/student/courses/exit/1", "method": "POST"}, # Exit course - adjust course_id
                {"path": "/api/courses/1/details", "method": "GET"} # View course details - adjust course_id
            ]
        }
        # Common endpoints for all users
        self.common_endpoints = [
            {"path": "/api/user/role", "method": "GET"},
            {"path": "/", "method": "GET"},
            {"path": "/assignments", "method": "GET"}, # Assignments page HTML
            {"path": "/course/1", "method": "GET"} # Course page HTML - adjust course_id
        ]
        # Public endpoints (no login required)
        self.public_endpoints = [
            {"path": "/login", "method": "GET"},
            {"path": "/register", "method": "GET"}
        ]

    def make_request(self, user_id):
        """Make random API requests to simulate user activity."""
        session = requests.Session()

        # Randomly select a user role and credentials
        user_data = random.choice(self.user_credentials)
        logged_in = False
        login_attempts = 0

        while self.running:
            try:
                # If not logged in, try to login or use public endpoints
                if not logged_in:
                    # Occasionally just hit public endpoints without logging in
                    if random.random() < 0.3 or login_attempts >= 3:
                        endpoint = random.choice(self.public_endpoints)
                    else:
                        # Try to log in
                        logging.info(f"User {user_id} attempting to log in as {user_data['role']}")
                        response = session.post(
                            f"{self.base_url}/login",
                            data={"username": user_data["username"], "password": user_data["password"]}
                        )
                        if response.status_code == 200:
                            logged_in = True
                            logging.info(f"User {user_id} logged in successfully as {user_data['role']}")
                            continue
                        else:
                            login_attempts += 1
                            logging.warning(f"Login failed for User {user_id}: {response.status_code}")
                            time.sleep(self.request_interval)
                            continue
                else:
                    # Select from role-specific or common endpoints
                    if random.random() < 0.7:  # 70% role-specific endpoints
                        endpoint = random.choice(self.role_endpoints.get(user_data["role"], []) + self.common_endpoints)
                    else:  # 30% common or public endpoints
                        endpoint = random.choice(self.common_endpoints + self.public_endpoints)

                    # Occasional logout
                    if random.random() < 0.05:  # 5% chance to logout
                        logging.info(f"User {user_id} logging out")
                        session.get(f"{self.base_url}/logout")
                        logged_in = False
                        # Pick a new random user for next login
                        user_data = random.choice(self.user_credentials)
                        login_attempts = 0
                        continue

                path = endpoint["path"]
                method = endpoint["method"]
                data = endpoint.get("data") # Get optional data for POST requests

                start_time = time.time()

                if method == "GET":
                    response = session.get(f"{self.base_url}{path}")
                elif method == "POST":
                    if data:
                        response = session.post(f"{self.base_url}{path}", data=data)
                    else:
                        response = session.post(f"{self.base_url}{path}")

                duration = time.time() - start_time

                status = "✓" if response.status_code < 400 else "✗"
                logging.info(f"User {user_id} ({user_data['role']}): {method} {path} - Status: {response.status_code} {status} - Time: {duration:.3f}s")

                # If we got a 401/403, we probably got logged out
                if response.status_code in [401, 403] and logged_in:
                    logged_in = False
                    logging.info(f"User {user_id} session expired or insufficient permissions")

                # Add some randomized waiting time
                time.sleep(self.request_interval * random.uniform(0.5, 1.5))

            except Exception as e:
                logging.error(f"Request failed for User {user_id}: {e}")
                time.sleep(self.request_interval)

    def start(self):
        """Start load generation with multiple concurrent users."""
        self.running = True
        threads = []

        logging.info(f"Starting load generation with {self.users} users making requests every ~{self.request_interval} seconds")

        for i in range(self.users):
            t = threading.Thread(target=self.make_request, args=(i,))
            t.daemon = True
            t.start()
            threads.append(t)
            # Stagger the user start times
            time.sleep(0.5)

        try:
            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            logging.info("Load generation stopped by user")
            self.running = False

        for t in threads:
            t.join(timeout=1)

        logging.info("Load generation complete")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Generate API load for testing')
    parser.add_argument('-u', '--users', type=int, default=5, help='Number of concurrent users')
    parser.add_argument('-i', '--interval', type=float, default=1.0, help='Time between requests (seconds)')
    parser.add_argument('-b', '--base-url', type=str, default='http://localhost:5000', help='Base URL for API')

    args = parser.parse_args()

    generator = APILoadGenerator(
        base_url=args.base_url,
        users=args.users,
        request_interval=args.interval
    )

    generator.start()