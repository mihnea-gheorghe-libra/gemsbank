const target = db.getSiblingDB("gems");

target.runCommand({
  collMod: "journalTransactions",
  validator: {
    $and: [
      {
        $jsonSchema: {
          bsonType: "object",
          required: [
            "_id",
            "currency",
            "kind",
            "entries",
            "reference",
            "counterparty",
            "category",
            "postedAt",
            "correlationId",
            "actor",
          ],
          properties: {
            _id: { bsonType: "string" },
            currency: { enum: ["RON", "EUR", "USD"] },
            kind: {
              enum: [
                "opening_deposit",
                "internal_transfer",
                "fee",
                "reversal",
                "fx_conversion",
                "demo_topup",
              ],
            },
            entries: {
              bsonType: "array",
              minItems: 2,
              items: {
                bsonType: "object",
                required: ["accountId", "amount"],
                properties: {
                  accountId: { bsonType: "string" },
                  amount: { bsonType: ["int", "long"] },
                },
              },
            },
            reference: { bsonType: "string" },
            counterparty: { bsonType: "string" },
            category: { bsonType: "string" },
            postedAt: { bsonType: "date" },
            correlationId: { bsonType: "string" },
            actor: { bsonType: "string" },
            reverses: { bsonType: ["string", "null"] },
          },
        },
      },
      { $expr: { $eq: [{ $sum: "$entries.amount" }, 0] } },
      { $expr: { $gte: [{ $size: "$entries" }, 2] } },
      {
        $expr: {
          $eq: [
            0,
            {
              $size: {
                $filter: {
                  input: "$entries",
                  cond: { $eq: ["$$this.amount", 0] },
                },
              },
            },
          ],
        },
      },
    ],
  },
  validationLevel: "strict",
  validationAction: "error",
});

print("011_demo_topup_kind applied — journalTransactions now also accepts \"demo_topup\".");
