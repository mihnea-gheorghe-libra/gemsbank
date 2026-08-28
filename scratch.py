from pymongo import MongoClient

client = MongoClient('mongodb://localhost:27017/?directConnection=true')
db = client['gems']

for a in db.accounts.find():
    print(f"ID: {a.get('_id')} - Name: {a.get('name')} - Status: {a.get('status')} - Daily: {a.get('dailyTransactedMinor')}")
