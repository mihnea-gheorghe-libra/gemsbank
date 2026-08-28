import datetime
from pymongo import MongoClient

client = MongoClient('mongodb://172.16.64.44:27018/?replicaSet=rs-gemsbank')
db = client['gems']

account_id_to_activate = '01a01ed4-9a3a-716e-ac40-bdcd6a7fad8e'
res = db.accounts.update_one({'_id': account_id_to_activate}, {'$set': {'status': 'active'}})
print(f'Activated account {account_id_to_activate}: modified {res.modified_count}')

user_id = '01a01ed4-99bc-728d-8a58-a239b290a161'
accounts = list(db.accounts.find({'userId': user_id}))
account_ids = [a['_id'] for a in accounts]

today = datetime.datetime.now(datetime.timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
query = {
    'entries.accountId': {'$in': account_ids},
    'postedAt': {'$gte': today}
}
txs = list(db.journalTransactions.find(query))
print(f'Found {len(txs)} transactions today.')

yesterday = today - datetime.timedelta(days=1)
modified = 0
for tx in txs:
    db.journalTransactions.update_one(
        {'_id': tx['_id']},
        {'$set': {'postedAt': yesterday}}
    )
    modified += 1

print(f'Shifted {modified} transactions to yesterday to reset the daily limit.')
