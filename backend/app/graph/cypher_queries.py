"""Cypher templates.

Labels and relationship types can't be parameterised in Cypher, so templates use
__LABEL__ / __PRED__ / __DEPTH__ placeholders that are filled only with values that
passed graph.base.safe_label / safe_rel_type / int validation.
"""

# --- Schema -------------------------------------------------------------------
SCHEMA_STATEMENTS = [
    "CREATE CONSTRAINT entity_key IF NOT EXISTS FOR (e:Entity) REQUIRE e.key IS UNIQUE",
    "CREATE CONSTRAINT chunk_id IF NOT EXISTS FOR (c:Chunk) REQUIRE c.id IS UNIQUE",
    "CREATE INDEX chunk_doc IF NOT EXISTS FOR (c:Chunk) ON (c.doc_id)",
    "CREATE FULLTEXT INDEX entity_names IF NOT EXISTS FOR (e:Entity) ON EACH [e.name]",
]

# --- Writes --------------------------------------------------------------------
UPSERT_ENTITIES = """
UNWIND $rows AS row
MERGE (e:Entity {key: row.key})
ON CREATE SET e.name = row.name, e.created_at = timestamp(), e.doc_ids = [], e.confidence = row.confidence
SET e:`__LABEL__`,
    e.confidence = CASE WHEN row.confidence > coalesce(e.confidence, 0) THEN row.confidence ELSE e.confidence END,
    e.doc_ids = coalesce(e.doc_ids, []) + [d IN row.doc_ids WHERE NOT d IN coalesce(e.doc_ids, [])],
    e.verified = coalesce(e.verified, false) OR row.verified,
    e.updated_at = timestamp()
WITH e, row
UNWIND row.chunks AS ch
MERGE (c:Chunk {id: ch.id})
ON CREATE SET c.doc_id = ch.doc_id
MERGE (e)-[:MENTIONED_IN]->(c)
"""

UPSERT_RELATIONS = """
UNWIND $rows AS row
MERGE (s:Entity {key: row.s_key})
ON CREATE SET s.name = row.s_name, s.created_at = timestamp(), s.doc_ids = [], s.confidence = row.confidence
MERGE (o:Entity {key: row.o_key})
ON CREATE SET o.name = row.o_name, o.created_at = timestamp(), o.doc_ids = [], o.confidence = row.confidence
SET s.doc_ids = coalesce(s.doc_ids, []) + [d IN [row.doc_id] WHERE d IS NOT NULL AND NOT d IN coalesce(s.doc_ids, [])],
    o.doc_ids = coalesce(o.doc_ids, []) + [d IN [row.doc_id] WHERE d IS NOT NULL AND NOT d IN coalesce(o.doc_ids, [])]
MERGE (s)-[r:`__PRED__`]->(o)
ON CREATE SET r.created_at = timestamp(), r.doc_ids = [], r.chunk_ids = [], r.confidence = row.confidence
SET r.confidence = CASE WHEN row.confidence > coalesce(r.confidence, 0) THEN row.confidence ELSE r.confidence END,
    r.doc_ids = coalesce(r.doc_ids, []) + [d IN [row.doc_id] WHERE d IS NOT NULL AND NOT d IN coalesce(r.doc_ids, [])],
    r.chunk_ids = coalesce(r.chunk_ids, []) + [c IN row.chunk_ids WHERE NOT c IN coalesce(r.chunk_ids, [])],
    r.verified = coalesce(r.verified, false) OR row.verified
"""

# --- Retrieval -----------------------------------------------------------------
FIND_ENTITIES_EXACT = """
MATCH (e:Entity) WHERE e.key IN $keys
RETURN e.key AS key, e.name AS name, [l IN labels(e) WHERE l <> 'Entity'][0] AS label, 10.0 AS score
"""

FIND_ENTITIES_FULLTEXT = """
CALL db.index.fulltext.queryNodes('entity_names', $q) YIELD node, score
WHERE node:Entity
RETURN node.key AS key, node.name AS name, [l IN labels(node) WHERE l <> 'Entity'][0] AS label, score
ORDER BY score DESC
LIMIT $limit
"""

NEIGHBOURHOOD = """
MATCH (e:Entity) WHERE e.key IN $keys
CALL {
  WITH e
  MATCH p = (e)-[*1..__DEPTH__]-(:Entity)
  WHERE none(x IN relationships(p) WHERE type(x) = 'MENTIONED_IN')
  RETURN p
  LIMIT $per_entity
}
WITH p
UNWIND relationships(p) AS r
WITH r, min(length(p)) AS hops
WHERE $doc_ids IS NULL OR any(d IN coalesce(r.doc_ids, []) WHERE d IN $doc_ids)
WITH r, hops, startNode(r) AS s, endNode(r) AS o
RETURN s.name AS subject,
       [l IN labels(s) WHERE l <> 'Entity'][0] AS subject_label,
       type(r) AS predicate,
       o.name AS object,
       [l IN labels(o) WHERE l <> 'Entity'][0] AS object_label,
       coalesce(r.confidence, 1.0) AS confidence,
       coalesce(r.doc_ids, []) AS doc_ids,
       hops
ORDER BY hops ASC, confidence DESC
LIMIT $limit
"""

# --- Deletes ---------------------------------------------------------------------
DELETE_DOC_RELATIONS = """
MATCH (:Entity)-[r]->(:Entity) WHERE $doc_id IN coalesce(r.doc_ids, [])
SET r.doc_ids = [d IN r.doc_ids WHERE d <> $doc_id]
WITH r WHERE size(r.doc_ids) = 0
DELETE r
"""

DELETE_DOC_CHUNKS = "MATCH (c:Chunk {doc_id: $doc_id}) DETACH DELETE c"

DELETE_DOC_ENTITIES = """
MATCH (e:Entity) WHERE $doc_id IN coalesce(e.doc_ids, [])
SET e.doc_ids = [d IN e.doc_ids WHERE d <> $doc_id]
WITH e WHERE size(e.doc_ids) = 0 AND NOT EXISTS { (e)--(:Entity) }
DETACH DELETE e
"""

# --- Metadata / stats -------------------------------------------------------------
COUNT_ENTITIES = "MATCH (e:Entity) RETURN count(e) AS c"
COUNT_RELATIONSHIPS = "MATCH (:Entity)-[r]->(:Entity) RETURN count(r) AS c"
COUNT_CHUNKS = "MATCH (c:Chunk) RETURN count(c) AS c"
COUNT_VERIFIED = "MATCH (e:Entity) WHERE e.verified = true RETURN count(e) AS c"
COUNT_ISOLATED = "MATCH (e:Entity) WHERE NOT EXISTS { (e)--(:Entity) } RETURN count(e) AS c"

NODE_COUNTS_BY_LABEL = """
MATCH (e:Entity) UNWIND labels(e) AS label
WITH label WHERE label <> 'Entity'
RETURN label, count(*) AS count ORDER BY count DESC
"""

REL_COUNTS_BY_TYPE = """
MATCH (:Entity)-[r]->(:Entity)
RETURN type(r) AS type, count(*) AS count ORDER BY count DESC
"""

TOP_ENTITIES_BY_DEGREE = """
MATCH (e:Entity)
OPTIONAL MATCH (e)-[r]-(:Entity)
WITH e, count(r) AS degree
ORDER BY degree DESC LIMIT $limit
RETURN e.name AS entity, [l IN labels(e) WHERE l <> 'Entity'][0] AS label, degree
"""

PROPERTY_KEYS = "CALL db.propertyKeys() YIELD propertyKey RETURN collect(propertyKey) AS keys"

SUBGRAPH = """
MATCH (s:Entity)-[r]->(o:Entity)
WHERE $key IS NULL OR s.key = $key OR o.key = $key
RETURN s.key AS s_key, s.name AS s_name, [l IN labels(s) WHERE l <> 'Entity'][0] AS s_label,
       type(r) AS type, coalesce(r.confidence, 1.0) AS confidence,
       o.key AS o_key, o.name AS o_name, [l IN labels(o) WHERE l <> 'Entity'][0] AS o_label
LIMIT $limit
"""
