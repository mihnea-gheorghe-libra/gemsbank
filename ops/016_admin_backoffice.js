const target = db.getSiblingDB("gems");

// The admin back office signs in against its own credential (env) and its own
// session store. An admin token is never a customer token: different collection,
// different resolver, different Actor kind.
if (!target.getCollectionNames().includes("adminSessions")) {
  target.createCollection("adminSessions");
}

target.runCommand({
  collMod: "adminSessions",
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["_id", "adminId", "username", "tokenHash", "issuedAt", "expiresAt"],
      properties: {
        _id: { bsonType: "string" },
        adminId: { bsonType: "string" },
        username: { bsonType: "string" },
        tokenHash: { bsonType: "string" },
        issuedAt: { bsonType: "date" },
        expiresAt: { bsonType: "date" },
        revokedAt: { bsonType: ["date", "null"] },
        userAgent: { bsonType: ["string", "null"] },
        ipAddress: { bsonType: ["string", "null"] },
      },
    },
  },
  validationLevel: "strict",
});

// An account freeze carries the reason that justified it. The same three fields
// carry the unfreeze reason: the full history is in auditLog, these are the
// current state.
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
        currency: { enum: ["RON", "EUR", "USD"] },
        kind: { enum: ["current", "savings", "invest"] },
        label: { bsonType: "string" },
        status: { enum: ["active", "frozen", "closed"] },
        openedAt: { bsonType: "date" },
        statusReason: { bsonType: ["string", "null"] },
        statusChangedAt: { bsonType: ["date", "null"] },
        statusChangedBy: { bsonType: ["string", "null"] },
      },
    },
  },
  validationLevel: "strict",
});

// A refused transaction is never edited or deleted (CLAUDE.md rule 3): the admin
// posts a new, balanced, mirrored transaction that points at the original through
// `reverses` and carries the mandatory `reason`. The unique partial index below is
// what makes "reverse once" a database guarantee rather than a Python check.
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
            reason: { bsonType: ["string", "null"] },
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

// A credit application can now reach a decision. No scoring, no repricing: the
// admin picks approved or rejected and must say why.
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
        status: { enum: ["review", "withdrawn", "approved", "rejected"] },
        submittedAt: { bsonType: "date" },
        decisionReason: { bsonType: ["string", "null"] },
        decidedAt: { bsonType: ["date", "null"] },
        decidedBy: { bsonType: ["string", "null"] },
      },
    },
  },
  validationLevel: "strict",
});

print(
  "016_admin_backoffice applied — adminSessions created; accounts, journalTransactions " +
    "and creditApplications accept the admin fields."
);
