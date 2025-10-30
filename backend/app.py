from flask import Flask, jsonify, request
from flask_cors import CORS
from pymongo import MongoClient
from bson.objectid import ObjectId
import os
from dotenv import load_dotenv
from datetime import datetime, timedelta

# --- Load environment variables ---
load_dotenv()

app = Flask(__name__)
CORS(app)  # Allow frontend to access backend

# --- MongoDB Configuration ---
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
DB_NAME = os.getenv("DB_NAME", "student_attendance_db")

client = MongoClient(MONGO_URI)
db = client[DB_NAME]

# Collections
students_collection = db.students
courses_collection = db.courses
attendance_collection = db.attendance


# --- Helper Functions ---
def is_valid_objectId(id_string):
    """Check if a string is a valid MongoDB ObjectId"""
    try:
        ObjectId(id_string)
        return True
    except:
        return False


# --- Test Route ---
@app.route('/')
def home():
    return jsonify({"message": "✅ Flask Backend Connected to MongoDB!"})


# ==============================
# 🧑‍🎓 STUDENT ROUTES
# ==============================

# Get all students
@app.route('/students', methods=['GET'])
def get_students():
    students = []
    for student in students_collection.find():
        student['_id'] = str(student['_id'])
        students.append(student)
    return jsonify(students)


# Add new student
@app.route('/students', methods=['POST'])
def add_student():
    data = request.json
    if not data:
        return jsonify({"error": "No data provided"}), 400

    required_fields = ["student_id", "first_name", "last_name", "email"]
    if not all(field in data and data[field] for field in required_fields):
        return jsonify({"error": "Missing required fields: student_id, first_name, last_name, email"}), 400

    # Ensure uniqueness
    if students_collection.find_one({"student_id": data["student_id"]}):
        return jsonify({"error": "Student with this ID already exists"}), 409
    if students_collection.find_one({"email": data["email"]}):
        return jsonify({"error": "Student with this email already exists"}), 409

    result = students_collection.insert_one(data)
    data['_id'] = str(result.inserted_id)
    return jsonify(data), 201


# ==============================
# 📘 COURSE ROUTES
# ==============================

# Get all courses
@app.route('/courses', methods=['GET'])
def get_courses():
    courses = []
    for course in courses_collection.find():
        course['_id'] = str(course['_id'])
        courses.append(course)
    return jsonify(courses)


# Add new course
@app.route('/courses', methods=['POST'])
def add_course():
    data = request.json
    if not data:
        return jsonify({"error": "No data provided"}), 400

    required_fields = ["course_code", "course_name"]
    if not all(field in data and data[field] for field in required_fields):
        return jsonify({"error": "Missing required fields: course_code, course_name"}), 400

    if courses_collection.find_one({"course_code": data["course_code"]}):
        return jsonify({"error": "Course with this code already exists"}), 409

    result = courses_collection.insert_one(data)
    data['_id'] = str(result.inserted_id)
    return jsonify(data), 201


# ==============================
# 📅 ATTENDANCE ROUTES
# ==============================

# Get all attendance records
@app.route('/attendance', methods=['GET'])
def get_all_attendance():
    records = []
    for record in attendance_collection.find():
        record['_id'] = str(record['_id'])
        record['student_id'] = str(record['student_id'])
        record['course_id'] = str(record['course_id'])
        if isinstance(record.get('date'), datetime):
            record['date'] = record['date'].isoformat()
        records.append(record)
    return jsonify(records)


# Get attendance by course and date
@app.route('/attendance/<course_id>/<date_str>', methods=['GET'])
def get_attendance_by_course_and_date(course_id, date_str):
    if not is_valid_objectId(course_id):
        return jsonify({"error": "Invalid course_id format"}), 400

    try:
        start = datetime.strptime(date_str, '%Y-%m-%d')
        end = start + timedelta(days=1)

        query = {
            "course_id": ObjectId(course_id),
            "date": {"$gte": start, "$lt": end}
        }

        records = []
        for record in attendance_collection.find(query):
            record['_id'] = str(record['_id'])
            record['student_id'] = str(record['student_id'])
            record['course_id'] = str(record['course_id'])
            record['date'] = record['date'].isoformat()
            records.append(record)
        return jsonify(records)

    except ValueError:
        return jsonify({"error": "Invalid date format. Use YYYY-MM-DD"}), 400


# Mark or update attendance
@app.route('/attendance', methods=['POST'])
def mark_attendance():
    data = request.json
    if not data:
        return jsonify({"error": "No data provided"}), 400

    required_fields = ["course_id", "date", "records"]
    if not all(field in data and data[field] for field in required_fields):
        return jsonify({"error": "Missing required fields: course_id, date, records"}), 400

    course_id = data['course_id']
    if not is_valid_objectId(course_id):
        return jsonify({"error": "Invalid course_id"}), 400

    try:
        attendance_date = datetime.strptime(data['date'], '%Y-%m-%d')
    except ValueError:
        return jsonify({"error": "Invalid date format. Use YYYY-MM-DD"}), 400

    processed = []
    for rec in data['records']:
        if not all(k in rec and rec[k] for k in ["student_id", "status"]):
            return jsonify({"error": "Each record must include student_id and status"}), 400

        student_id = rec['student_id']
        if not is_valid_objectId(student_id):
            return jsonify({"error": f"Invalid student_id: {student_id}"}), 400

        if not students_collection.find_one({"_id": ObjectId(student_id)}):
            return jsonify({"error": f"Student not found: {student_id}"}), 404
        if not courses_collection.find_one({"_id": ObjectId(course_id)}):
            return jsonify({"error": f"Course not found: {course_id}"}), 404

        attendance_collection.update_one(
            {"student_id": ObjectId(student_id),
             "course_id": ObjectId(course_id),
             "date": attendance_date},
            {"$set": {
                "status": rec['status'],
                "notes": rec.get("notes", "")
            }},
            upsert=True
        )

        processed.append({
            "student_id": student_id,
            "course_id": course_id,
            "date": attendance_date.isoformat(),
            "status": rec['status'],
            "notes": rec.get("notes", "")
        })

    return jsonify({"message": "Attendance saved successfully", "processed_records": processed}), 200


# ==============================
# 🚀 RUN APP
# ==============================
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=True, port=port, host='0.0.0.0')
