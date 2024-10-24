class Node:
    def __init__(self, rule):
        self.rule = rule

    def evaluate(self, data):
        return eval(self.rule, {}, data)

def create_rule(rule_str):
    return Node(rule_str)

def evaluate_rule(node, data):
    return node.evaluate(data)

def combine_rules(nodes, operator):
    if operator == "AND":
        return all(node.evaluate(data) for node in nodes)
    elif operator == "OR":
        return any(node.evaluate(data) for node in nodes)
    else:
        raise ValueError("Unknown operator")
