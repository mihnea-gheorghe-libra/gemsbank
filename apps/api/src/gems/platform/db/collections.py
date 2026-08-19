from gems.platform.db.client import get_db

def users_collection():
    return get_db()["users"]

def accounts_collection():
    return get_db()["accounts"]

def transactions_collection():
    return get_db()["transactions"]

# etc. pentru kycCases, payees, cards, conversations, agentActions, insights, products, auditLog, sessions