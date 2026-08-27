const target = db.getSiblingDB("gems");

let linked = 0;
let unlinked = 0;

target.cards.find({ accountId: { $exists: false } }).forEach(function (card) {
  let account = target.accounts
    .find({ userId: card.userId, kind: "current", status: "active" })
    .sort({ openedAt: 1 })
    .limit(1)
    .next();
  if (!account) {
    account = target.accounts
      .find({ userId: card.userId, status: "active" })
      .sort({ openedAt: 1 })
      .limit(1)
      .next();
  }
  if (account) {
    target.cards.updateOne({ _id: card._id }, { $set: { accountId: account._id } });
    linked += 1;
  } else {
    print("WARNING: no active account found for card " + card._id + " (user " + card.userId + ") — left unlinked");
    unlinked += 1;
  }
});

target.runCommand({
  collMod: "cards",
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: [
        "_id",
        "userId",
        "accountId",
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
        accountId: { bsonType: "string" },
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

print("010_cards_account_link applied — " + linked + " card(s) backfilled, " + unlinked + " left unlinked (no active account found).");
