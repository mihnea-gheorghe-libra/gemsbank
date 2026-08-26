const target = db.getSiblingDB("gems");

target.runCommand({
  collMod: "accounts",
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: [
        "_id",
        "userId",
        "iban",
        "holderName",
        "currency",
        "kind",
        "label",
        "status",
        "openedAt",
      ],
      properties: {
        _id: { bsonType: "string" },
        userId: { bsonType: "string" },
        iban: { bsonType: "string", pattern: "^[A-Z]{2}[0-9]{2}[A-Z0-9]{11,30}$" },
        holderName: { bsonType: "string" },
        currency: { enum: ["RON", "EUR"] },
        kind: { enum: ["current", "savings", "invest"] },
        label: { bsonType: "string" },
        status: { enum: ["active", "frozen", "closed"] },
        openedAt: { bsonType: "date" },
      },
    },
  },
  validationLevel: "strict",
});

print("008_accounts_invest_kind applied — accounts.kind now also accepts \"invest\".");
