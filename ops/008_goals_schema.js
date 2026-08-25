const target = db.getSiblingDB("gems");

target.createCollection("goals");

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
        createdAt: { bsonType: "date" },
      },
    },
  },
  validationLevel: "strict",
});

target.goals.createIndex({ userId: 1 }, { unique: true, name: "uq_user" });

print("008_goals_schema applied");
