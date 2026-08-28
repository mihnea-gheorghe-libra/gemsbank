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
                "investment_buy",
                "investment_sell",
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

target.createCollection("investmentOrders");

target.runCommand({
  collMod: "investmentOrders",
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: [
        "_id",
        "userId",
        "accountId",
        "instrumentId",
        "side",
        "quantityMicro",
        "unitPriceMinor",
        "amountMinor",
        "currency",
        "journalTransactionId",
        "executedAt",
      ],
      properties: {
        _id: { bsonType: "string" },
        userId: { bsonType: "string" },
        accountId: { bsonType: "string" },
        instrumentId: { bsonType: "string" },
        side: { enum: ["buy", "sell"] },
        quantityMicro: { bsonType: ["int", "long"], minimum: 1 },
        unitPriceMinor: { bsonType: ["int", "long"], minimum: 1 },
        amountMinor: { bsonType: ["int", "long"], minimum: 1 },
        currency: { enum: ["RON", "EUR", "USD"] },
        journalTransactionId: { bsonType: "string" },
        executedAt: { bsonType: "date" },
      },
    },
  },
  validationLevel: "strict",
  validationAction: "error",
});

print("013_investments_trading applied — journalTransactions now also accepts \"investment_buy\" / \"investment_sell\", and investmentOrders exists with a schema validator.");
