const target = db.getSiblingDB("gems");

target.createCollection("creditApplications");

target.runCommand({
  collMod: "creditApplications",
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: [
        "_id",
        "userId",
        "productId",
        "kind",
        "amountMinorUnits",
        "rateBps",
        "purpose",
        "payoutAccountId",
        "currency",
        "status",
        "submittedAt",
      ],
      properties: {
        _id: { bsonType: "string" },
        userId: { bsonType: "string" },
        productId: { bsonType: "string" },
        kind: { enum: ["loan", "line"] },
        amountMinorUnits: { bsonType: ["int", "long"], minimum: 1 },
        termMonths: { bsonType: ["int", "long", "null"] },
        rateBps: { bsonType: ["int", "long"], minimum: 0 },
        purpose: { bsonType: "string" },
        payoutAccountId: { bsonType: "string" },
        currency: { enum: ["RON", "EUR", "USD"] },
        status: { enum: ["review", "withdrawn"] },
        submittedAt: { bsonType: "date" },
      },
    },
  },
  validationLevel: "strict",
});

target.creditApplications.createIndex(
  { userId: 1, submittedAt: -1 },
  { name: "ix_user_submitted" }
);

print("015_credit_applications_schema applied — creditApplications collection created.");
