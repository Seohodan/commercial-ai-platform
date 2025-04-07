import os
import json
import datetime
import random
from flask import Flask, request, jsonify, render_template, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.sql import func
from flask_cors import CORS
from werkzeug.middleware.proxy_fix import ProxyFix

# Initialize Flask app
app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app)
CORS(app)

# Configure SQLite database (will be created in current directory)
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'commercial_ai_experiments.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize database
db = SQLAlchemy(app)

# Define database models
class User(db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    department = db.Column(db.String(100), default='')
    profile_picture = db.Column(db.String(255), default='')
    created_at = db.Column(db.DateTime, default=func.now())

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'email': self.email,
            'department': self.department,
            'profile_picture': self.profile_picture,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

# Association table for many-to-many relationship between experiments and users
experiment_users = db.Table('experiment_users',
    db.Column('experiment_id', db.Integer, db.ForeignKey('experiments.id'), primary_key=True),
    db.Column('user_id', db.Integer, db.ForeignKey('users.id'), primary_key=True)
)

class Experiment(db.Model):
    __tablename__ = 'experiments'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    state = db.Column(db.String(20), default='Running')  # Running, Stopped, Completed, Archived
    experiment_type = db.Column(db.String(50), nullable=False)  # Fixed Horizon, Group Sequential
    stage = db.Column(db.String(50), default='Discovery')  # Discovery, Pre-launch, Phase 1, etc.
    department = db.Column(db.String(50), default='')  # Marketing, Sales, Procurement, etc.
    
    # Impact data stored as JSON
    impact_value = db.Column(db.Float, default=0)
    impact_positive_bound = db.Column(db.Float, default=0)
    impact_negative_bound = db.Column(db.Float, default=0)
    
    confidence = db.Column(db.Float, default=0)
    progress = db.Column(db.Float, default=0)
    
    # Participants data
    participants_count = db.Column(db.Integer, default=0)
    participants_target = db.Column(db.Integer, default=30)
    sample_size_reached = db.Column(db.Boolean, default=False)
    
    # Duration data
    duration_weeks = db.Column(db.Integer, default=8)
    duration_days = db.Column(db.Integer, default=0)
    
    significance = db.Column(db.String(20), default='Medium')  # Low, Medium, High
    analysis_type = db.Column(db.String(50), default='A/B Test')  # A/B Test, Multivariate, Feature Flag, Custom
    
    boundaries_crossed = db.Column(db.String(255), default='')  # Comma-separated list of crossed boundaries
    
    created_at = db.Column(db.DateTime, default=func.now())
    updated_at = db.Column(db.DateTime, default=func.now(), onupdate=func.now())
    
    # Relationships
    owners = db.relationship('User', secondary=experiment_users, backref=db.backref('experiments', lazy='dynamic'))
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'state': self.state,
            'experimentType': self.experiment_type,
            'stage': self.stage,
            'department': self.department,
            'impact': {
                'value': self.impact_value,
                'positiveBound': self.impact_positive_bound,
                'negativeBound': self.impact_negative_bound
            },
            'confidence': self.confidence,
            'progress': self.progress,
            'participants': {
                'count': self.participants_count,
                'target': self.participants_target,
                'sampleSizeReached': self.sample_size_reached
            },
            'duration': {
                'weeks': self.duration_weeks,
                'days': self.duration_days
            },
            'significance': self.significance,
            'analysisType': self.analysis_type,
            'boundariesCrossed': self.boundaries_crossed.split(',') if self.boundaries_crossed else [],
            'owners': [owner.to_dict() for owner in self.owners],
            'createdAt': self.created_at.isoformat() if self.created_at else None,
            'updatedAt': self.updated_at.isoformat() if self.updated_at else None
        }

# API Routes
@app.route('/api/experiments', methods=['GET'])
def get_experiments():
    # Get filter parameters
    state = request.args.get('state')
    significance = request.args.get('significance')
    owner_id = request.args.get('owner')
    analysis_type = request.args.get('analysisType')
    stage = request.args.get('stage')
    department = request.args.get('department')
    search = request.args.get('search', '')
    
    # Start with base query
    query = Experiment.query
    
    # Apply filters
    if state and state != 'Any':
        query = query.filter(Experiment.state == state)
    if significance and significance != 'Any':
        query = query.filter(Experiment.significance == significance)
    if analysis_type and analysis_type != 'Any':
        query = query.filter(Experiment.analysis_type == analysis_type)
    if stage and stage != 'Any':
        query = query.filter(Experiment.stage == stage)
    if department and department != 'Any':
        query = query.filter(Experiment.department == department)
    if owner_id and owner_id != 'Any':
        query = query.filter(Experiment.owners.any(User.id == owner_id))
    if search:
        query = query.filter(Experiment.name.ilike(f'%{search}%'))
    
    # Sort by created_at in descending order (newest first)
    query = query.order_by(Experiment.created_at.desc())
    
    # Execute query
    experiments = query.all()
    
    # Convert to dictionary
    result = [exp.to_dict() for exp in experiments]
    
    return jsonify(experiments=result, total=len(result))

@app.route('/api/experiments/<int:experiment_id>', methods=['GET'])
def get_experiment(experiment_id):
    experiment = Experiment.query.get_or_404(experiment_id)
    return jsonify(experiment.to_dict())

@app.route('/api/experiments', methods=['POST'])
def create_experiment():
    data = request.json
    
    # Extract nested fields
    impact = data.get('impact', {})
    participants = data.get('participants', {})
    duration = data.get('duration', {})
    owner_ids = data.get('owners', [])
    
    # Create experiment
    experiment = Experiment(
        name=data.get('name', 'New Experiment'),
        state=data.get('state', 'Running'),
        experiment_type=data.get('experimentType', 'Fixed Horizon'),
        stage=data.get('stage', 'Discovery'),
        department=data.get('department', 'Marketing'),
        impact_value=impact.get('value', 0),
        impact_positive_bound=impact.get('positiveBound', 0),
        impact_negative_bound=impact.get('negativeBound', 0),
        confidence=data.get('confidence', 0),
        progress=data.get('progress', 0),
        participants_count=participants.get('count', 0),
        participants_target=participants.get('target', 30),
        sample_size_reached=participants.get('sampleSizeReached', False),
        duration_weeks=duration.get('weeks', 8),
        duration_days=duration.get('days', 0),
        significance=data.get('significance', 'Medium'),
        analysis_type=data.get('analysisType', 'A/B Test')
    )
    
    # Add owners
    if owner_ids:
        owners = User.query.filter(User.id.in_(owner_ids)).all()
        for owner in owners:
            experiment.owners.append(owner)
    
    db.session.add(experiment)
    db.session.commit()
    
    return jsonify(experiment.to_dict()), 201

@app.route('/api/experiments/<int:experiment_id>', methods=['PUT'])
def update_experiment(experiment_id):
    experiment = Experiment.query.get_or_404(experiment_id)
    data = request.json
    
    # Update simple fields
    if 'name' in data:
        experiment.name = data['name']
    if 'state' in data:
        experiment.state = data['state']
    if 'experimentType' in data:
        experiment.experiment_type = data['experimentType']
    if 'stage' in data:
        experiment.stage = data['stage']
    if 'department' in data:
        experiment.department = data['department']
    if 'confidence' in data:
        experiment.confidence = data['confidence']
    if 'progress' in data:
        experiment.progress = data['progress']
    if 'significance' in data:
        experiment.significance = data['significance']
    if 'analysisType' in data:
        experiment.analysis_type = data['analysisType']
    
    # Update nested fields
    if 'impact' in data:
        impact = data['impact']
        if 'value' in impact:
            experiment.impact_value = impact['value']
        if 'positiveBound' in impact:
            experiment.impact_positive_bound = impact['positiveBound']
        if 'negativeBound' in impact:
            experiment.impact_negative_bound = impact['negativeBound']
    
    if 'participants' in data:
        participants = data['participants']
        if 'count' in participants:
            experiment.participants_count = participants['count']
        if 'target' in participants:
            experiment.participants_target = participants['target']
        if 'sampleSizeReached' in participants:
            experiment.sample_size_reached = participants['sampleSizeReached']
    
    if 'duration' in data:
        duration = data['duration']
        if 'weeks' in duration:
            experiment.duration_weeks = duration['weeks']
        if 'days' in duration:
            experiment.duration_days = duration['days']
    
    # Update boundaries crossed
    if 'boundariesCrossed' in data:
        experiment.boundaries_crossed = ','.join(data['boundariesCrossed'])
    
    # Update owners if provided
    if 'owners' in data:
        owner_ids = data['owners']
        experiment.owners = []  # Clear existing owners
        
        if owner_ids:
            owners = User.query.filter(User.id.in_(owner_ids)).all()
            for owner in owners:
                experiment.owners.append(owner)
    
    # Update timestamp
    experiment.updated_at = func.now()
    
    db.session.commit()
    return jsonify(experiment.to_dict())

@app.route('/api/experiments/<int:experiment_id>', methods=['DELETE'])
def delete_experiment(experiment_id):
    experiment = Experiment.query.get_or_404(experiment_id)
    db.session.delete(experiment)
    db.session.commit()
    return jsonify({'message': 'Experiment deleted successfully'})

@app.route('/api/users', methods=['GET'])
def get_users():
    users = User.query.all()
    return jsonify([user.to_dict() for user in users])

# Directly serve CSS - this helps ensure CSS content type is set correctly
@app.route('/static/styles.css')
def serve_css():
    return send_from_directory('static', 'styles.css')

# Placeholder images for avatars - direct serving for compatibility
@app.route('/static/avatar1.png')
def serve_avatar1():
    return "placeholder", 200, {'Content-Type': 'image/png'}

@app.route('/static/avatar2.png')
def serve_avatar2():
    return "placeholder", 200, {'Content-Type': 'image/png'}

@app.route('/static/avatar3.png')
def serve_avatar3():
    return "placeholder", 200, {'Content-Type': 'image/png'}

@app.route('/static/avatar4.png')
def serve_avatar4():
    return "placeholder", 200, {'Content-Type': 'image/png'}

@app.route('/static/avatar5.png')
def serve_avatar5():
    return "placeholder", 200, {'Content-Type': 'image/png'}

# Serve the index page
@app.route('/')
def serve_frontend():
    return render_template('index.html')

# Make sure directories exist
os.makedirs(os.path.join(basedir, 'static'), exist_ok=True)
os.makedirs(os.path.join(basedir, 'templates'), exist_ok=True)

# Create DB tables and sample data
def init_db():
    # Force recreate the database to ensure we have the sample data
    db_path = os.path.join(basedir, 'commercial_ai_experiments.db')
    if os.path.exists(db_path):
        os.remove(db_path)

    with app.app_context():
        db.create_all()
        
        # Create sample users with departments
        users = [
            User(name="John Doe", email="john@example.com", department="Marketing", profile_picture="/static/avatar1.png"),
            User(name="Maya Patel", email="maya@example.com", department="Sales", profile_picture="/static/avatar2.png"),
            User(name="Robert Chen", email="robert@example.com", department="Procurement", profile_picture="/static/avatar3.png"),
            User(name="Sarah Kim", email="sarah@example.com", department="Operations", profile_picture="/static/avatar4.png"),
            User(name="David Wilson", email="david@example.com", department="IT", profile_picture="/static/avatar5.png")
        ]
        db.session.add_all(users)
        db.session.commit()
        
        # Get saved users for relationships
        [user1, user2, user3, user4, user5] = User.query.all()
        
        # Enterprise AI experiments focused on business departments
        experiments = [
            # Marketing AI experiments
            {
                "name": "Campaign Smart Targeting ML",
                "experiment_type": "Fixed Horizon",
                "state": "Running",
                "department": "Marketing",
                "stage": "Phase 2",
                "impact_value": 12.4,
                "impact_positive_bound": 15.7,
                "impact_negative_bound": -1.2,
                "confidence": 98.3,
                "progress": 82,
                "participants_count": 38,
                "participants_target": 45,
                "sample_size_reached": False,
                "duration_weeks": 6,
                "duration_days": 3,
                "significance": "High",
                "analysis_type": "A/B Test",
                "owners": [user1, user5]
            },
            {
                "name": "Personalized Email Subject Lines",
                "experiment_type": "Group Sequential",
                "state": "Running",
                "department": "Marketing",
                "stage": "Phase 1",
                "impact_value": 8.2,
                "impact_positive_bound": 10.5,
                "impact_negative_bound": -1.8,
                "confidence": 92.1,
                "progress": 45,
                "participants_count": 22,
                "participants_target": 40,
                "sample_size_reached": False,
                "duration_weeks": 4,
                "duration_days": 2,
                "significance": "Medium",
                "analysis_type": "Multivariate",
                "owners": [user1]
            },
            {
                "name": "Adobe vs Salesforce Marketing Cloud",
                "experiment_type": "Fixed Horizon",
                "state": "Running",
                "department": "Marketing",
                "stage": "Pilot",
                "impact_value": 5.3,
                "impact_positive_bound": 7.1,
                "impact_negative_bound": -1.5,
                "confidence": 88.4,
                "progress": 75,
                "participants_count": 26,
                "participants_target": 30,
                "sample_size_reached": False,
                "duration_weeks": 8,
                "duration_days": 0,
                "significance": "Medium",
                "analysis_type": "Vendor Comparison",
                "owners": [user1, user5]
            },
            
            # Sales AI experiments
            {
                "name": "Lead Scoring Algorithm Update",
                "experiment_type": "Group Sequential",
                "state": "Running",
                "department": "Sales",
                "stage": "Scale",
                "impact_value": 18.7,
                "impact_positive_bound": 22.3,
                "impact_negative_bound": -1.1,
                "confidence": 99.7,
                "progress": 100,
                "participants_count": 42,
                "participants_target": 40,
                "sample_size_reached": True,
                "duration_weeks": 12,
                "duration_days": 0,
                "significance": "High",
                "analysis_type": "A/B Test",
                "owners": [user2]
            },
            {
                "name": "HubSpot vs Salesforce CRM Integration",
                "experiment_type": "Fixed Horizon",
                "state": "Stopped",
                "department": "Sales",
                "stage": "Pre-launch",
                "impact_value": -2.3,
                "impact_positive_bound": 1.8,
                "impact_negative_bound": -5.6,
                "confidence": 87.2,
                "progress": 65,
                "participants_count": 18,
                "participants_target": 30,
                "sample_size_reached": False,
                "duration_weeks": 4,
                "duration_days": 5,
                "significance": "Low",
                "analysis_type": "Vendor Comparison",
                "owners": [user2, user5]
            },
            {
                "name": "Sales Conversation Intelligence",
                "experiment_type": "Fixed Horizon",
                "state": "Running",
                "department": "Sales",
                "stage": "Discovery",
                "impact_value": 4.5,
                "impact_positive_bound": 6.8,
                "impact_negative_bound": -1.2,
                "confidence": 58.4,
                "progress": 28,
                "participants_count": 12,
                "participants_target": 35,
                "sample_size_reached": False,
                "duration_weeks": 7,
                "duration_days": 0,
                "significance": "Medium",
                "analysis_type": "Feature Flag",
                "owners": [user2, user1]
            },
            
            # Procurement AI experiments
            {
                "name": "Spend Analytics Dashboard",
                "experiment_type": "Fixed Horizon",
                "state": "Running",
                "department": "Procurement",
                "stage": "Pilot",
                "impact_value": 9.6,
                "impact_positive_bound": 11.2,
                "impact_negative_bound": -0.7,
                "confidence": 98.9,
                "progress": 94,
                "participants_count": 45,
                "participants_target": 45,
                "sample_size_reached": True,
                "duration_weeks": 10,
                "duration_days": 4,
                "significance": "High",
                "analysis_type": "A/B Test",
                "owners": [user3]
            },
            {
                "name": "Coupa vs SAP Ariba for PO Processing",
                "experiment_type": "Group Sequential",
                "state": "Running",
                "department": "Procurement",
                "stage": "Phase 3",
                "impact_value": 7.8,
                "impact_positive_bound": 9.5,
                "impact_negative_bound": -1.4,
                "confidence": 95.6,
                "progress": 77,
                "participants_count": 28,
                "participants_target": 30,
                "sample_size_reached": False,
                "duration_weeks": 9,
                "duration_days": 1,
                "significance": "Medium",
                "analysis_type": "Vendor Comparison",
                "owners": [user3, user5]
            },
            {
                "name": "Supplier Risk Assessment Model",
                "experiment_type": "Fixed Horizon",
                "state": "Completed",
                "department": "Procurement",
                "stage": "Scale",
                "impact_value": 21.4,
                "impact_positive_bound": 24.8,
                "impact_negative_bound": -0.8,
                "confidence": 99.9,
                "progress": 100,
                "participants_count": 30,
                "participants_target": 30,
                "sample_size_reached": True,
                "duration_weeks": 16,
                "duration_days": 3,
                "significance": "High",
                "analysis_type": "Custom",
                "owners": [user3, user4]
            },
            
            # Operations AI experiments
            {
                "name": "Real-time Inventory Prediction",
                "experiment_type": "Group Sequential",
                "state": "Running",
                "department": "Operations",
                "stage": "Phase 2",
                "impact_value": 8.9,
                "impact_positive_bound": 10.5,
                "impact_negative_bound": -1.8,
                "confidence": 97.3,
                "progress": 72,
                "participants_count": 31,
                "participants_target": 40,
                "sample_size_reached": False,
                "duration_weeks": 11,
                "duration_days": 0,
                "significance": "High",
                "analysis_type": "Multivariate",
                "owners": [user4]
            },
            {
                "name": "Blue Yonder vs Manhattan Warehouse AI",
                "experiment_type": "Fixed Horizon",
                "state": "Running",
                "department": "Operations",
                "stage": "Discovery",
                "impact_value": 3.2,
                "impact_positive_bound": 5.4,
                "impact_negative_bound": -2.1,
                "confidence": 67.7,
                "progress": 32,
                "participants_count": 16,
                "participants_target": 40,
                "sample_size_reached": False,
                "duration_weeks": 5,
                "duration_days": 2,
                "significance": "Medium",
                "analysis_type": "Vendor Comparison",
                "owners": [user4, user5]
            },
            {
                "name": "Delivery Route Optimization",
                "experiment_type": "Fixed Horizon",
                "state": "Completed",
                "department": "Operations",
                "stage": "Scale",
                "impact_value": 15.3,
                "impact_positive_bound": 17.8,
                "impact_negative_bound": -1.2,
                "confidence": 99.8,
                "progress": 100,
                "participants_count": 35,
                "participants_target": 35,
                "sample_size_reached": True,
                "duration_weeks": 14,
                "duration_days": 2,
                "significance": "High",
                "analysis_type": "A/B Test",
                "owners": [user4, user3]
            },
            
            # IT/Cross-functional AI experiments
            {
                "name": "Internal vs Cloud ML Models",
                "experiment_type": "Fixed Horizon",
                "state": "Running",
                "department": "IT",
                "stage": "Phase 1",
                "impact_value": 6.8,
                "impact_positive_bound": 8.9,
                "impact_negative_bound": -1.6,
                "confidence": 91.2,
                "progress": 58,
                "participants_count": 24,
                "participants_target": 40,
                "sample_size_reached": False,
                "duration_weeks": 13,
                "duration_days": 0,
                "significance": "Medium",
                "analysis_type": "Vendor Comparison",
                "owners": [user5, user1]
            },
            {
                "name": "Azure ML vs AWS Sagemaker",
                "experiment_type": "Group Sequential",
                "state": "Running",
                "department": "IT",
                "stage": "Pre-launch",
                "impact_value": 2.4,
                "impact_positive_bound": 4.7,
                "impact_negative_bound": -2.4,
                "confidence": 73.5,
                "progress": 40,
                "participants_count": 18,
                "participants_target": 36,
                "sample_size_reached": False,
                "duration_weeks": 8,
                "duration_days": 3,
                "significance": "Low",
                "analysis_type": "Vendor Comparison",
                "owners": [user5]
            }
        ]
        
        # Create sample experiment objects
        experiment_objects = []
        for exp_data in experiments:
            owners = exp_data.pop('owners')
            exp = Experiment(**exp_data)
            for owner in owners:
                exp.owners.append(owner)
            experiment_objects.append(exp)
        
        db.session.add_all(experiment_objects)
        db.session.commit()

# Initialize the database
init_db()

if __name__ == '__main__':
    # For local development
    print("Starting Commercial AI Experimentation Platform...")
    print("Access the application at http://localhost:8080")
    app.run(debug=True, host='0.0.0.0', port=8080)
