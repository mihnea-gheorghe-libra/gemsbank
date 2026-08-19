const target = db.getSiblingDB("gems");

function centuryFromGenderDigit(digit) {
  if (digit === "1" || digit === "2") return 1900;
  if (digit === "3" || digit === "4") return 1800;
  if (digit === "5" || digit === "6") return 2000;
  return null;
}

function toIsoDate(ddmmyyyy) {
  const parts = String(ddmmyyyy).split(".");
  if (parts.length !== 3) return null;
  return parts[2] + "-" + parts[1] + "-" + parts[0];
}

let backfilled = 0;
let dropped = 0;

target.kycCases.find({ "document.extracted": { $exists: true } }).forEach((doc) => {
  const extracted = doc.document.extracted;
  if (extracted.birthDate) return;

  const cnp = String(extracted.cnpMasked || "");
  const century = centuryFromGenderDigit(cnp.charAt(0));
  const year = century === null ? null : century + parseInt(cnp.substring(1, 3), 10);
  const month = cnp.substring(3, 5);
  const expiresOn = toIsoDate(extracted.expiresOn);

  if (year === null || isNaN(year) || !/^\d{2}$/.test(month) || expiresOn === null) {
    target.kycCases.deleteOne({ _id: doc._id });
    dropped += 1;
    return;
  }

  target.kycCases.updateOne(
    { _id: doc._id },
    {
      $set: {
        "document.extracted.birthDate": year + "-" + month + "-01",
        "document.extracted.expiresOn": expiresOn,
      },
    }
  );
  backfilled += 1;
});

target.runCommand({
  collMod: "kycCases",
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["_id", "status", "createdAt", "updatedAt"],
      properties: {
        _id: { bsonType: "string" },
        status: {
          enum: [
            "started",
            "document_submitted",
            "contact_provided",
            "code_verified",
            "completed",
          ],
        },
        document: {
          bsonType: ["object", "null"],
          required: ["docRef", "docType", "extracted", "submittedAt"],
          properties: {
            docRef: { bsonType: "string" },
            docType: { bsonType: "string" },
            submittedAt: { bsonType: "date" },
            extracted: {
              bsonType: "object",
              required: [
                "fullName",
                "birthDate",
                "cnpMasked",
                "documentNumberMasked",
                "expiresOn",
              ],
              properties: {
                fullName: { bsonType: "string" },
                birthDate: { bsonType: "string", pattern: "^[0-9]{4}-[0-9]{2}-[0-9]{2}$" },
                cnpMasked: { bsonType: "string" },
                documentNumberMasked: { bsonType: "string" },
                expiresOn: { bsonType: "string", pattern: "^[0-9]{4}-[0-9]{2}-[0-9]{2}$" },
              },
            },
          },
        },
        contact: {
          bsonType: ["object", "null"],
          required: ["email", "phone"],
          properties: {
            email: { bsonType: "string" },
            phone: { bsonType: "string" },
          },
        },
        otp: {
          bsonType: ["object", "null"],
          required: ["codeHash", "expiresAt", "sentAt", "attempts", "resends"],
          properties: {
            codeHash: { bsonType: "string" },
            expiresAt: { bsonType: "date" },
            sentAt: { bsonType: "date" },
            attempts: { bsonType: "int" },
            resends: { bsonType: "int" },
          },
        },
        userId: { bsonType: ["string", "null"] },
        createdAt: { bsonType: "date" },
        updatedAt: { bsonType: "date" },
      },
    },
  },
  validationLevel: "strict",
});

print("002_extracted_birth_date applied — backfilled " + backfilled + ", dropped " + dropped);
