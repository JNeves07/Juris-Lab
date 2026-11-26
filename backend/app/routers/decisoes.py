"""Leitura de decisões, tribunais, estatísticas e ações rápidas."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app import db
from app.schemas import StatusIn

router = APIRouter()


@router.get("/api/tribunais")
def tribunais():
    return db.q("SELECT id, sigla, nome, ramo, uf FROM tribunais ORDER BY ramo, sigla")


@router.get("/api/decisoes/{decisao_id}")
def decisao(decisao_id: int):
    d = db.q(
        """SELECT d.*, t.sigla AS tribunal, t.nome AS tribunal_nome, oj.nome AS orgao_julgador,
                  EXISTS (SELECT 1 FROM favoritos f WHERE f.decisao_id = d.id) AS favorito
           FROM decisoes d
           JOIN tribunais t ON t.id = d.tribunal_id
           LEFT JOIN orgaos_julgadores oj ON oj.id = d.orgao_julgador_id
           WHERE d.id = %s""",
        (decisao_id,),
        one=True,
    )
    if not d:
        raise HTTPException(404, "Decisão não encontrada")
    d.pop("busca", None)
    d["anotacoes"] = db.q(
        "SELECT id, texto, trecho, criada_em FROM anotacoes WHERE decisao_id=%s ORDER BY criada_em",
        (decisao_id,),
    )
    d["tags"] = db.q(
        "SELECT g.id, g.nome FROM tags g JOIN decisao_tag dt ON dt.tag_id=g.id "
        "WHERE dt.decisao_id=%s ORDER BY g.nome",
        (decisao_id,),
    )
    d["pastas"] = db.q(
        "SELECT p.id, p.nome FROM pastas p JOIN decisao_pasta dp ON dp.pasta_id=p.id "
        "WHERE dp.decisao_id=%s ORDER BY p.nome",
        (decisao_id,),
    )
    d["relacoes"] = db.q(
        """SELECT r.id, r.tipo, r.nota, 'saida' AS direcao, o.id AS outra_id,
                  t.sigla AS tribunal, o.numero_processo, o.classe
           FROM relacoes_decisoes r JOIN decisoes o ON o.id = r.destino_id JOIN tribunais t ON t.id = o.tribunal_id
           WHERE r.origem_id = %(id)s
           UNION ALL
           SELECT r.id, r.tipo, r.nota, 'entrada', o.id, t.sigla, o.numero_processo, o.classe
           FROM relacoes_decisoes r JOIN decisoes o ON o.id = r.origem_id JOIN tribunais t ON t.id = o.tribunal_id
           WHERE r.destino_id = %(id)s""",
        {"id": decisao_id},
    )
    d["historico"] = db.q(
        "SELECT campo, alterado_em FROM historico_alteracoes "
        "WHERE decisao_id=%s ORDER BY alterado_em DESC LIMIT 20",
        (decisao_id,),
    )
    return d


@router.get("/api/estatisticas")
def estatisticas():
    linha = db.q(
        "SELECT reltuples::bigint AS n FROM pg_class WHERE relname='decisoes'", one=True
    ) or {}
    total = linha.get("n")
    # reltuples = -1 sinaliza estatística desatualizada no PostgreSQL.
    if total is None or total < 0:
        total = (db.q("SELECT count(*) AS n FROM decisoes", one=True) or {}).get("n", 0)
    return {
        "decisoes": total,
        "por_tribunal": db.q(
            """SELECT t.sigla, count(*) AS n FROM decisoes d JOIN tribunais t ON t.id=d.tribunal_id
               GROUP BY t.sigla ORDER BY n DESC LIMIT 15"""
        ),
        "ultima_coleta": db.q(
            "SELECT fonte, finalizada_em, inseridas, atualizadas FROM coletas ORDER BY id DESC LIMIT 5"
        ),
    }


@router.put("/api/decisoes/{decisao_id}/favorito")
def favoritar(decisao_id: int):
    db.q(
        "INSERT INTO favoritos (decisao_id) VALUES (%s) ON CONFLICT DO NOTHING",
        (decisao_id,),
        write=True,
    )
    return {"ok": True}


@router.delete("/api/decisoes/{decisao_id}/favorito")
def desfavoritar(decisao_id: int):
    db.q("DELETE FROM favoritos WHERE decisao_id=%s", (decisao_id,), write=True)
    return {"ok": True}


@router.put("/api/decisoes/{decisao_id}/status")
def mudar_status(decisao_id: int, body: StatusIn):
    db.q(
        "UPDATE decisoes SET status=%s::status_vigencia WHERE id=%s",
        (body.status, decisao_id),
        write=True,
    )
    return {"ok": True}
