"""Pastas, tags, anotações, relações e buscas salvas."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from psycopg.types.json import Jsonb

from app import db
from app.schemas import BuscaSalva, Nome, Relacao, Texto

router = APIRouter()


@router.get("/api/pastas")
def listar_pastas():
    return db.q(
        """SELECT p.id, p.nome, p.pai_id, count(dp.decisao_id) AS total
           FROM pastas p LEFT JOIN decisao_pasta dp ON dp.pasta_id = p.id
           GROUP BY p.id ORDER BY p.nome"""
    )


@router.post("/api/pastas")
def criar_pasta(body: Nome):
    return db.q(
        "INSERT INTO pastas (nome, pai_id) VALUES (%s,%s) RETURNING id, nome, pai_id",
        (body.nome, body.pai_id),
    )[0]


@router.delete("/api/pastas/{pasta_id}")
def apagar_pasta(pasta_id: int):
    db.q("DELETE FROM pastas WHERE id=%s", (pasta_id,), write=True)
    return {"ok": True}


@router.put("/api/decisoes/{decisao_id}/pastas/{pasta_id}")
def pasta_add(decisao_id: int, pasta_id: int):
    db.q(
        "INSERT INTO decisao_pasta VALUES (%s,%s) ON CONFLICT DO NOTHING",
        (decisao_id, pasta_id),
        write=True,
    )
    return {"ok": True}


@router.delete("/api/decisoes/{decisao_id}/pastas/{pasta_id}")
def pasta_del(decisao_id: int, pasta_id: int):
    db.q(
        "DELETE FROM decisao_pasta WHERE decisao_id=%s AND pasta_id=%s",
        (decisao_id, pasta_id),
        write=True,
    )
    return {"ok": True}


@router.get("/api/tags")
def listar_tags():
    return db.q(
        """SELECT g.id, g.nome, count(dt.decisao_id) AS total
           FROM tags g LEFT JOIN decisao_tag dt ON dt.tag_id = g.id
           GROUP BY g.id ORDER BY g.nome"""
    )


@router.put("/api/decisoes/{decisao_id}/tags")
def tag_add(decisao_id: int, body: Nome):
    nome = body.nome.strip().lower()
    if not nome:
        raise HTTPException(400, "Tag vazia")
    tag = db.q(
        "INSERT INTO tags (nome) VALUES (%s) ON CONFLICT (nome) DO UPDATE SET nome=EXCLUDED.nome RETURNING id, nome",
        (nome,),
    )[0]
    db.q(
        "INSERT INTO decisao_tag VALUES (%s,%s) ON CONFLICT DO NOTHING",
        (decisao_id, tag["id"]),
        write=True,
    )
    return tag


@router.delete("/api/decisoes/{decisao_id}/tags/{tag_id}")
def tag_del(decisao_id: int, tag_id: int):
    db.q(
        "DELETE FROM decisao_tag WHERE decisao_id=%s AND tag_id=%s",
        (decisao_id, tag_id),
        write=True,
    )
    return {"ok": True}


@router.post("/api/decisoes/{decisao_id}/anotacoes")
def anotar(decisao_id: int, body: Texto):
    return db.q(
        "INSERT INTO anotacoes (decisao_id, texto, trecho) VALUES (%s,%s,%s) "
        "RETURNING id, texto, trecho, criada_em",
        (decisao_id, body.texto, body.trecho),
    )[0]


@router.delete("/api/anotacoes/{anotacao_id}")
def apagar_anotacao(anotacao_id: int):
    db.q("DELETE FROM anotacoes WHERE id=%s", (anotacao_id,), write=True)
    return {"ok": True}


@router.post("/api/decisoes/{decisao_id}/relacoes")
def relacionar(decisao_id: int, body: Relacao):
    if body.destino_id == decisao_id:
        raise HTTPException(400, "Uma decisão não pode relacionar-se consigo mesma.")
    db.q(
        """INSERT INTO relacoes_decisoes (origem_id, destino_id, tipo, nota)
           VALUES (%s,%s,%s::tipo_relacao,%s) ON CONFLICT DO NOTHING""",
        (decisao_id, body.destino_id, body.tipo, body.nota),
        write=True,
    )
    return {"ok": True}


@router.delete("/api/relacoes/{relacao_id}")
def apagar_relacao(relacao_id: int):
    db.q("DELETE FROM relacoes_decisoes WHERE id=%s", (relacao_id,), write=True)
    return {"ok": True}


@router.get("/api/buscas-salvas")
def buscas_salvas():
    return db.q("SELECT id, nome, consulta, filtros FROM buscas_salvas ORDER BY nome")


@router.post("/api/buscas-salvas")
def salvar_busca(body: BuscaSalva):
    return db.q(
        "INSERT INTO buscas_salvas (nome, consulta, filtros) VALUES (%s,%s,%s) RETURNING id, nome",
        (body.nome, body.consulta, Jsonb(body.filtros)),
    )[0]


@router.delete("/api/buscas-salvas/{busca_id}")
def apagar_busca(busca_id: int):
    db.q("DELETE FROM buscas_salvas WHERE id=%s", (busca_id,), write=True)
    return {"ok": True}
