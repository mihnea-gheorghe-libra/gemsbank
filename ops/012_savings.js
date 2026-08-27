const target = db.getSiblingDB("gems");

target.goals.updateMany(
  { parentAccountId: { $exists: false } },
  [{ $set: { parentAccountId: "$accountId" } }]
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
        "parentAccountId",
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
        parentAccountId: { bsonType: "string" },
        name: { bsonType: "string" },
        targetMinorUnits: { bsonType: ["int", "long"], minimum: 1 },
        currency: { enum: ["RON", "EUR", "USD"] },
        targetDate: { bsonType: "date" },
        status: { enum: ["active", "closed"] },
        createdAt: { bsonType: "date" },
        closedAt: { bsonType: ["date", "null"] },
      },
    },
  },
  validationLevel: "strict",
});

const names = target.getCollectionNames();
if (names.indexOf("standingOrders") < 0) {
  target.createCollection("standingOrders");
}

target.runCommand({
  collMod: "standingOrders",
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: [
        "_id",
        "goalId",
        "userId",
        "sourceAccountId",
        "targetAccountId",
        "amountMinorUnits",
        "currency",
        "frequency",
        "nextRunAt",
        "status",
        "createdVia",
        "createdAt",
        "updatedAt",
      ],
      properties: {
        _id: { bsonType: "string" },
        goalId: { bsonType: "string" },
        userId: { bsonType: "string" },
        sourceAccountId: { bsonType: "string" },
        targetAccountId: { bsonType: "string" },
        amountMinorUnits: { bsonType: ["int", "long"], minimum: 1 },
        currency: { enum: ["RON", "EUR", "USD"] },
        frequency: { enum: ["weekly", "monthly"] },
        nextRunAt: { bsonType: "date" },
        status: { enum: ["active", "paused", "cancelled"] },
        createdVia: { enum: ["user", "agent-suggestion-confirmed"] },
        createdAt: { bsonType: "date" },
        updatedAt: { bsonType: "date" },
        lastRunAt: { bsonType: ["date", "null"] },
        lastFailureReason: { bsonType: ["string", "null"] },
      },
    },
  },
  validationLevel: "strict",
});

print("012_savings applied — goals now carry parentAccountId, and standingOrders exists.");
