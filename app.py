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
                "analysis_type":
