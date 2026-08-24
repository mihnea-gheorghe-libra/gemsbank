const target = db.getSiblingDB("gems");

let backfilled = 0;
target.users.find({ fullName: { $exists: false } }).forEach((user) => {
  const kyc = target.kycCases.findOne({ _id: user.kycCaseId });
  const fullName = kyc && kyc.document && kyc.document.extracted && kyc.document.extracted.fullName;
  if (fullName) {
    target.users.updateOne({ _id: user._id }, { $set: { fullName: fullName } });
    backfilled += 1;
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
        "fullName",
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
        fullName: { bsonType: "string" },
        passwordHash: { bsonType: "string" },
        pinHash: { bsonType: "string" },
        pinEncrypted: { bsonType: ["string", "null"] },
        kycCaseId: { bsonType: "string" },
        prefs: { bsonType: "object" },
        signIn: { bsonType: "object" },
        pin: { bsonType: "object" },
        password: { bsonType: "object" },
        status: { enum: ["active", "suspended", "locked"] },
        createdAt: { bsonType: "date" },
      },
    },
  },
  validationLevel: "moderate",
});

print("007_users_full_name applied — backfilled fullName on " + backfilled + " user(s) from their KYC case.");
