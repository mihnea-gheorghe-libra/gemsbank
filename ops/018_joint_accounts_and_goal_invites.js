const target = db.getSiblingDB("gems");

// A shared savings goal opens a real account with more than one owner. `kind` gains
// "joint" and the account gains `ownerIds` — the creator stays in `userId` (unchanged
// everywhere else in the app), accepted collaborators land in `ownerIds`.
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
        kind: { enum: ["current", "savings", "invest", "joint"] },
        label: { bsonType: "string" },
        status: { enum: ["active", "frozen", "closed"] },
        openedAt: { bsonType: "date" },
        statusReason: { bsonType: ["string", "null"] },
        statusChangedAt: { bsonType: ["date", "null"] },
        statusChangedBy: { bsonType: ["string", "null"] },
        ownerIds: { bsonType: ["array", "null"], items: { bsonType: "string" } },
      },
    },
  },
  validationLevel: "strict",
});

// One pending/accepted/declined row per invited collaborator on a shared goal. Never
// updated in place beyond its status + respondedAt — the invite itself is immutable
// history, same append-only spirit as the rest of the system.
if (!target.getCollectionNames().includes("goalInvites")) {
  target.createCollection("goalInvites");
}

target.runCommand({
  collMod: "goalInvites",
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: [
        "_id",
        "goalId",
        "goalName",
        "currency",
        "inviterId",
        "inviterName",
        "inviteeId",
        "inviteeUsername",
        "shareKind",
        "status",
        "createdAt",
      ],
      properties: {
        _id: { bsonType: "string" },
        goalId: { bsonType: "string" },
        goalName: { bsonType: "string" },
        currency: { enum: ["RON", "EUR", "USD"] },
        inviterId: { bsonType: "string" },
        inviterName: { bsonType: "string" },
        inviteeId: { bsonType: "string" },
        inviteeUsername: { bsonType: "string" },
        shareKind: { enum: ["fixed", "percent"] },
        shareAmountMinorUnits: { bsonType: ["int", "long", "null"] },
        sharePercentBp: { bsonType: ["int", "long", "null"] },
        status: { enum: ["pending", "accepted", "declined"] },
        createdAt: { bsonType: "date" },
        respondedAt: { bsonType: ["date", "null"] },
      },
    },
  },
  validationLevel: "strict",
});

print("018_joint_accounts_and_goal_invites applied");
