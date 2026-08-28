const target = db.getSiblingDB("gems");

target.createCollection("termDeposits");

target.runCommand({
  collMod: "termDeposits",
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: [
        "_id",
        "userId",
        "accountId",
        "parentAccountId",
        "name",
        "rateBps",
        "termMonths",
        "currency",
        "maturesAt",
        "status",
        "createdAt",
      ],
      properties: {
        _id: { bsonType: "string" },
        userId: { bsonType: "string" },
        accountId: { bsonType: "string" },
        parentAccountId: { bsonType: "string" },
        name: { bsonType: "string" },
        rateBps: { bsonType: ["int", "long"], minimum: 0 },
        termMonths: { bsonType: ["int", "long"], minimum: 1 },
        currency: { enum: ["RON", "EUR", "USD"] },
        maturesAt: { bsonType: "date" },
        status: { enum: ["active", "closed"] },
        createdAt: { bsonType: "date" },
        closedAt: { bsonType: ["date", "null"] },
      },
    },
  },
  validationLevel: "strict",
});

target.termDeposits.createIndex({ userId: 1, createdAt: 1 }, { name: "ix_user_created" });

print("014_term_deposits_schema applied — termDeposits collection created.");
