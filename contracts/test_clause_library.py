from m1.clause_library import ClauseLibrary


library = ClauseLibrary.from_json(
    "data/clause_library.json"
)

clauses = library.list_approved()

print(f"Approved clauses: {len(clauses)}")

print()

for clause in clauses:
    print(
        clause.clause_id,
        "|",
        clause.type,
        "|",
        clause.jurisdiction,
        "|",
        clause.document_types,
    )

print()

clause = library.get("CLZ-CONF-EG-001")

print("Selected clause:")
print("ID:", clause.clause_id)
print("Type:", clause.type)
print("Jurisdiction:", clause.jurisdiction)
print("Version:", clause.version)
print("Status:", clause.approval_status)
print("Arabic:", clause.text_ar)
print("English:", clause.text_en)