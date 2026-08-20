const target = db.getSiblingDB("gems");

target.createCollection("cards");

target.runCommand({
  collMod: "cards",
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: [
        "_id",
        "userId",
        "kind",
        "last4",
        "ownerName",
        "currency",
        "expiresOn",
        "state",
        "pinEncrypted",
        "atmLimitMinor",
        "onlineLimitMinor",
        "createdAt",
        "updatedAt",
      ],
      properties: {
        _id: { bsonType: "string" },
        userId: { bsonType: "string" },
        kind: {
          enum: [
            "physical_debit",
            "virtual_mastercard",
            "virtual_single_use",
            "physical_metal",
          ],
        },
        last4: { bsonType: "string" },
        ownerName: { bsonType: "string" },
        currency: { bsonType: "string" },
        expiresOn: { bsonType: "string" },
        state: { enum: ["active", "frozen", "blocked"] },
        pinEncrypted: { bsonType: "string" },
        atmLimitMinor: { bsonType: ["int", "long"] },
        onlineLimitMinor: { bsonType: ["int", "long"] },
        createdAt: { bsonType: "date" },
        updatedAt: { bsonType: "date" },
      },
    },
  },
  validationLevel: "strict",
});

print("004_cards_schema applied");
