const target = db.getSiblingDB("gems");

target.cards.updateMany(
  { cvvEncrypted: { $exists: false } },
  { $set: { cvvEncrypted: null } }
);

const withoutCvv = target.cards.countDocuments({ cvvEncrypted: null });

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
        cvvEncrypted: { bsonType: ["string", "null"] },
        atmLimitMinor: { bsonType: ["int", "long"] },
        onlineLimitMinor: { bsonType: ["int", "long"] },
        createdAt: { bsonType: "date" },
        updatedAt: { bsonType: "date" },
      },
    },
  },
  validationLevel: "strict",
});

print(
  "005_cards_cvv applied — " + withoutCvv + " card(s) have no cvvEncrypted and cannot show CVV"
);
