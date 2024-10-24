from flask import Flask, request, jsonify, render_template
from flask_sqlalchemy import SQLAlchemy
from flask_socketio import SocketIO, send
import json
from datetime import datetime
from custom_rule_engine import Node, create_rule, evaluate_rule, combine_rules  # Updated import

app = Flask(__name__)
app.config['SECRET_KEY'] = 'mysecret'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///rules.db'
db = SQLAlchemy(app)
socketio = SocketIO(app)

# Database model for rules
class Rule(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    rule_id = db.Column(db.String(50), unique=True, nullable=False)
    rule_ast = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

# Initialize the database within the application context
with app.app_context():
    db.create_all()

# Store rules in memory for the current session
rules = {}

@app.route('/')
def index():
    return render_template('chat.html')

@app.route('/rules', methods=['GET'])
def get_rules():
    rules_db = Rule.query.all()
    rules_list = [{"rule_id": rule.rule_id, "rule_ast": rule.rule_ast, "created_at": rule.created_at} for rule in rules_db]
    return render_template('rules.html', rules=rules_list)

@app.route('/clear_rules', methods=['POST'])
def clear_rules():
    try:
        db.session.query(Rule).delete()
        db.session.commit()
        return jsonify({"message": "All rules cleared successfully."}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

def dict_to_node(data):
    if data is None:
        return None
    node_type = data.get('node_type')
    value = data.get('value')
    left = dict_to_node(data.get('left'))
    right = dict_to_node(data.get('right'))
    return Node(node_type=node_type, value=value, left=left, right=right)

@socketio.on('message')
def handle_message(msg):
    print(f"Received message: {msg}")
    try:
        if 'create rule' in msg.lower():
            rule_string = msg.split("create rule: ")[1]
            ast = create_rule(rule_string)
            rule_ast_json = json.dumps(ast, default=lambda o: o.__dict__)
            existing_rule = Rule.query.filter_by(rule_ast=rule_ast_json).first()

            if existing_rule:
                send(f"Error: A rule with the same logic already exists as '{existing_rule.rule_id}'.")
            else:
                last_rule = Rule.query.order_by(Rule.id.desc()).first()
                rule_id = f"rule{last_rule.id + 1 if last_rule else 1}"
                rules[rule_id] = ast
                new_rule = Rule(rule_id=rule_id, rule_ast=rule_ast_json)
                db.session.add(new_rule)
                db.session.commit()
                send(f"Rule created: {rule_id}")

        elif 'evaluate rule' in msg.lower():
            parts = msg.split(":", 2)
            rule_name = parts[1].strip()
            user_data_str = parts[2].strip()
            user_data = json.loads(user_data_str)

            if rule_name not in rules:
                rule = Rule.query.filter_by(rule_id=rule_name).first()
                if rule:
                    rules[rule_name] = dict_to_node(json.loads(rule.rule_ast))

            if rule_name in rules:
                result = evaluate_rule(rules[rule_name], user_data)
                send(f"Evaluation result: {result}")
            else:
                send(f"Error: Rule '{rule_name}' not found.")

        elif 'combine rules' in msg.lower():
            parts = msg.split(":", 2)
            rule_names_str = parts[1].strip()
            operator = parts[2].strip()

            rule_names = [rule_name.strip() for rule_name in rule_names_str.split(',')]
            asts = []

            for rule_name in rule_names:
                if rule_name in rules:
                    asts.append(rules[rule_name])
                else:
                    rule = Rule.query.filter_by(rule_id=rule_name).first()
                    if rule:
                        ast = json.loads(rule.rule_ast)
                        rules[rule_name] = dict_to_node(ast)
                        asts.append(rules[rule_name])
                    else:
                        send(f"Error: Rule '{rule_name}' not found.")
                        return

            combined_ast = combine_rules(asts, operator)
            last_rule = Rule.query.order_by(Rule.id.desc()).first()
            new_rule_id = f"rule{last_rule.id + 1 if last_rule else 1}"

            rules[new_rule_id] = combined_ast
            combined_rule = Rule(rule_id=new_rule_id, rule_ast=json.dumps(combined_ast, default=lambda o: o.__dict__))
            db.session.add(combined_rule)
            db.session.commit()

            send(f"Rules combined into new rule: {new_rule_id}")

        else:
            send(f"Unrecognized command: {msg}")

    except json.JSONDecodeError as e:
        send(f"Error evaluating rule: Invalid JSON - {str(e)}")
        print(f"JSON parsing error: {str(e)}")
    except Exception as e:
        send(f"Error: {str(e)}")
        print(f"Error: {str(e)}")

if __name__ == '__main__':
    socketio.run(app, debug=True)
