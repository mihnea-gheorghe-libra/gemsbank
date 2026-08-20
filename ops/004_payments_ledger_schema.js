const target = db.getSiblingDB("gems");

target.createCollection("sessions");

target.runCommand({
  collMod: "sessions",
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["_id", "userId", "tokenHash", "issuedAt", "expiresAt"],
      properties: {
        _id: { bsonType: "string" },
        userId: { bsonType: "string" },
        tokenHash: { bsonType: "string" },
        issuedAt: { bsonType: "date" },
        expiresAt: { bsonType: "date" },
        revokedAt: { bsonType: ["date", "null"] },
      },
    },
  },
  validationLevel: "strict",
});

target.createCollection("accounts");

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
        kind: { enum: ["current", "savings"] },
        label: { bsonType: "string" },
        status: { enum: ["active", "frozen", "closed"] },
        openedAt: { bsonType: "date" },
      },
    },
  },
  validationLevel: "strict",
});

target.createCollection("journalTransactions");

// Double entry is enforced here, not only in Python (CLAUDE.md rule 2). A v0
// transaction is single-currency, so "sums to zero per currency" is one $sum
// over the embedded entries. $expr runs on every insert; there is no update
// path in the repository, and none may be added: the journal is append-only.
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
            currency: { enum: ["RON", "EUR"] },
            kind: {
              enum: ["opening_deposit", "internal_transfer", "fee", "reversal"],
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

target.createCollection("payments");

target.runCommand({
  collMod: "payments",
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: [
        "_id",
        "userId",
        "rail",
        "status",
        "sourceAccountId",
        "targetIban",
        "counterparty",
        "amountMinorUnits",
        "currency",
        "reference",
        "category",
        "payeeCheck",
        "createdAt",
        "updatedAt",
      ],
      properties: {
        _id: { bsonType: "string" },
        userId: { bsonType: "string" },
        rail: { enum: ["internal", "sepa"] },
        status: {
          enum: ["draft", "awaiting_signature", "pending", "posted", "rejected"],
        },
        sourceAccountId: { bsonType: "string" },
        targetAccountId: { bsonType: ["string", "null"] },
        targetIban: { bsonType: "string" },
        counterparty: { bsonType: "string" },
        amountMinorUnits: { bsonType: ["int", "long"], minimum: 1 },
        currency: { enum: ["RON", "EUR"] },
        reference: { bsonType: "string" },
        category: { bsonType: "string" },
        payeeCheck: { enum: ["match", "close_match", "no_match", "not_checked"] },
        signature: {
          bsonType: ["object", "null"],
          required: ["codeHash", "expiresAt", "issuedAt", "attempts"],
          properties: {
            codeHash: { bsonType: "string" },
            expiresAt: { bsonType: "date" },
            issuedAt: { bsonType: "date" },
            attempts: { bsonType: "int" },
          },
        },
        journalTransactionId: { bsonType: ["string", "null"] },
        rejectedReason: { bsonType: ["string", "null"] },
        createdAt: { bsonType: "date" },
        updatedAt: { bsonType: "date" },
      },
    },
  },
  validationLevel: "strict",
});

target.createCollection("beneficiaries");

target.runCommand({
  collMod: "beneficiaries",
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["_id", "userId", "name", "iban", "createdAt"],
      properties: {
        _id: { bsonType: "string" },
        userId: { bsonType: "string" },
        name: { bsonType: "string" },
        iban: { bsonType: "string", pattern: "^[A-Z]{2}[0-9]{2}[A-Z0-9]{11,30}$" },
        createdAt: { bsonType: "date" },
      },
    },
  },
  validationLevel: "strict",
});

// The mandates collection exists with no rows: PROMPT.md 7.3. Agent mandates
// are evaluated by the same policy interface the human flows already use.
target.createCollection("mandates");

print("004_payments_ledger_schema applied");
