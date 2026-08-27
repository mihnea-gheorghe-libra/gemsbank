const target = db.getSiblingDB("gems");

target.goals.updateMany(
  { status: { $exists: false } },
  { $set: { status: "active" } }
);

target.runCommand({
  collMod: "goals",
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: [
        "_id",
        "userId",
        "accountId",
        "name",
        "targetMinorUnits",
        "currency",
        "targetDate",
        "status",
        "createdAt",
      ],
      properties: {
        _id: { bsonType: "string" },
        userId: { bsonType: "string" },
        accountId: { bsonType: "string" },
        name: { bsonType: "string" },
        targetMinorUnits: { bsonType: ["int", "long"], minimum: 1 },
        currency: { enum: ["RON", "EUR"] },
        targetDate: { bsonType: "date" },
        status: { enum: ["active", "closed"] },
        createdAt: { bsonType: "date" },
        closedAt: { bsonType: ["date", "null"] },
      },
    },
  },
  validationLevel: "strict",
});

target.goals.dropIndex("uq_user");
target.goals.createIndex(
  { userId: 1 },
  { unique: true, name: "uq_user_active", partialFilterExpression: { status: "active" } }
);

print("011_goals_status applied");
