const target = db.getSiblingDB("gems");

let backfilled = 0;
let unmatched = 0;

target.users.find({ identity: { $exists: false } }).forEach(function (user) {
  const kycCase = target.kycCases.findOne({ _id: user.kycCaseId });
  const extracted = kycCase && kycCase.document && kycCase.document.extracted;

  if (!extracted) {
    unmatched += 1;
    return;
  }

  target.users.updateOne(
    { _id: user._id },
    {
      $set: {
        identity: {
          fullName: extracted.fullName,
          birthDate: extracted.birthDate,
          cnpMasked: extracted.cnpMasked,
          documentNumberMasked: extracted.documentNumberMasked,
          documentExpiresOn: extracted.expiresOn,
        },
      },
    }
  );
  backfilled += 1;
});

target.accounts.find({}).forEach(function (account) {
  const owner = target.users.findOne({ _id: account.userId });
  if (owner && owner.identity && owner.identity.fullName !== account.holderName) {
    target.accounts.updateOne(
      { _id: account._id },
      { $set: { holderName: owner.identity.fullName } }
    );
  }
});

target.cards.find({}).forEach(function (card) {
  const owner = target.users.findOne({ _id: card.userId });
  if (owner && owner.identity && owner.identity.fullName !== card.ownerName) {
    target.cards.updateOne(
      { _id: card._id },
      { $set: { ownerName: owner.identity.fullName } }
    );
  }
});

target.runCommand({
  collMod: "users",
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: [
        "_id",
        "username",
        "email",
        "phone",
        "passwordHash",
        "pinHash",
        "kycCaseId",
        "status",
        "createdAt",
      ],
      properties: {
        _id: { bsonType: "string" },
        username: { bsonType: "string" },
        email: { bsonType: "string" },
        phone: { bsonType: "string" },
        passwordHash: { bsonType: "string" },
        pinHash: { bsonType: "string" },
        pinEncrypted: { bsonType: ["string", "null"] },
        kycCaseId: { bsonType: "string" },
        identity: {
          bsonType: "object",
          required: [
            "fullName",
            "birthDate",
            "cnpMasked",
            "documentNumberMasked",
            "documentExpiresOn",
          ],
          properties: {
            fullName: { bsonType: "string" },
            birthDate: { bsonType: "string" },
            cnpMasked: { bsonType: "string" },
            documentNumberMasked: { bsonType: "string" },
            documentExpiresOn: { bsonType: "string" },
          },
        },
        prefs: { bsonType: "object" },
        pin: {
          bsonType: "object",
          required: ["failures", "locked"],
          properties: {
            failures: { bsonType: "int" },
            locked: { bsonType: "bool" },
          },
        },
        password: {
          bsonType: "object",
          required: ["failures", "lockoutStage", "lockedUntil"],
          properties: {
            failures: { bsonType: "int" },
            lockoutStage: { bsonType: "int" },
            lockedUntil: { bsonType: ["date", "null"] },
          },
        },
        status: { enum: ["active", "suspended", "locked"] },
        createdAt: { bsonType: "date" },
      },
    },
  },
  validationLevel: "strict",
});

print(
  "006_user_identity applied — " +
    backfilled +
    " user(s) backfilled from their KYC case, " +
    unmatched +
    " without an extracted document (they will show no identity on /me)"
);
