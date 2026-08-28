const target = db.getSiblingDB("gems");

// Phase 2 root cause: 011 dropped "uq_user", but on databases where 011 never ran the
// unique-per-user index from 008 survives and blocks every goal after the first one,
// closed or not. Any unique index on goals is legacy now; goals are many-per-user.
target.goals
  .getIndexes()
  .filter((index) => index.name !== "_id_" && index.unique)
  .forEach((index) => target.goals.dropIndex(index.name));

target.goals.updateMany(
  { streakWeeks: { $exists: false } },
  { $set: { streakWeeks: 0, streakLastWeek: null, streakComputedAt: null } }
);

target.runCommand({
  collMod: "goals",
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: [
        "_id",
        "userId",
        "accountId",
        "parentAccountId",
        "name",
        "targetMinorUnits",
        "currency",
        "targetDate",
        "status",
        "createdAt",
      ],
      properties: {
        _id: { bsonType: "string" },
        userId: { bsonType: "string" },
        accountId: { bsonType: "string" },
        parentAccountId: { bsonType: "string" },
        name: { bsonType: "string" },
        targetMinorUnits: { bsonType: ["int", "long"], minimum: 1 },
        currency: { enum: ["RON", "EUR", "USD"] },
        targetDate: { bsonType: "date" },
        status: { enum: ["active", "closed"] },
        createdAt: { bsonType: "date" },
        closedAt: { bsonType: ["date", "null"] },
        streakWeeks: { bsonType: ["int", "long"], minimum: 0 },
        streakLastWeek: { bsonType: ["string", "null"] },
        streakComputedAt: { bsonType: ["date", "null"] },
      },
    },
  },
  validationLevel: "strict",
});

print("013_goals_multi_and_streak applied — many active goals per user, streak persisted.");
