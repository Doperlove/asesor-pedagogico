"""Rúbrica parametrizada y cálculo de la nota en el backend."""
import copy

import pytest

from app.grading import calcular_nota, nivel_por_metrica, redondear
from app.rubrics import RubricaSchema, rubrica_sha256, validar_rubrica


def test_rubrica_valida(rubrica_valida):
    r = validar_rubrica(rubrica_valida, {"RA1", "RA2", "RA3", "RA4"})
    assert r.valida, r.errores
    assert r.errores == []


def test_pesos_deben_sumar_100(rubrica_valida):
    rubrica_valida["criterios"][0]["peso"] = 40
    r = validar_rubrica(rubrica_valida)
    assert not r.valida
    assert any("suman 115" in e for e in r.errores)


@pytest.mark.parametrize("mutacion,fragmento", [
    (lambda r: r["criterios"][1]["niveles"][2].update(descriptor=""), "no tiene descriptor"),
    (lambda r: r["criterios"][2].update(competencia_id="RA9"), "no existe en la rúbrica"),
    (lambda r: r["criterios"][3]["niveles"][0].pop("umbral_min"), "umbral_min"),
    (lambda r: r["criterios"][0]["niveles"].reverse(), "de menor a mayor"),
    (lambda r: r["criterios"][0]["niveles"][1].update(puntaje=7), "fuera de 0,0–5,0"),
    (lambda r: r["criterios"].append(copy.deepcopy(r["criterios"][0])), "Criterio duplicado"),
    (lambda r: r["criterios"][0].update(niveles=r["criterios"][0]["niveles"][:1]), "al menos 2 niveles"),
    (lambda r: r["criterios"][0]["niveles"][1].update(descriptor=r["criterios"][0]["niveles"][0]["descriptor"]), "idénticos"),
])
def test_rubricas_incoherentes_se_rechazan(rubrica_valida, mutacion, fragmento):
    mutacion(rubrica_valida)
    r = validar_rubrica(rubrica_valida)
    assert not r.valida
    assert any(fragmento in e for e in r.errores), r.errores


def test_json_malformado_se_rechaza():
    r = validar_rubrica("{no es json")
    assert not r.valida and "JSON inválido" in r.errores[0]


def test_advertencia_competencia_fuera_de_catalogo(rubrica_valida):
    r = validar_rubrica(rubrica_valida, {"RA1"})
    assert r.valida
    assert any("catálogo" in a for a in r.advertencias)


def test_hash_estable_e_independiente_del_orden(rubrica_valida):
    reordenada = dict(reversed(list(rubrica_valida.items())))
    assert rubrica_sha256(rubrica_valida) == rubrica_sha256(reordenada)


def test_formula_de_la_nota(rubrica_valida):
    rub = RubricaSchema.model_validate(rubrica_valida)
    # CR1 25% N4(5.0), CR2 20% N3(4.0), CR3 20% N2(3.0), CR4 20% N4(5.0), CR5 15% N1(1.5)
    res = calcular_nota(rub, {"CR1": "N4", "CR2": "N3", "CR3": "N2", "CR4": "N4", "CR5": "N1"})
    esperado = 0.25 * 5 + 0.20 * 4 + 0.20 * 3 + 0.20 * 5 + 0.15 * 1.5
    assert res["nota_sin_redondeo"] == pytest.approx(esperado)
    assert res["nota"] == 3.9


def test_nota_maxima_y_minima(rubrica_valida):
    rub = RubricaSchema.model_validate(rubrica_valida)
    assert calcular_nota(rub, {c.id: c.niveles[-1].id for c in rub.criterios})["nota"] == 5.0
    assert calcular_nota(rub, {c.id: c.niveles[0].id for c in rub.criterios})["nota"] == 1.5


def test_nivel_faltante_lanza_error(rubrica_valida):
    rub = RubricaSchema.model_validate(rubrica_valida)
    with pytest.raises(ValueError):
        calcular_nota(rub, {"CR1": "N4"})


def test_redondeo_half_up():
    assert redondear(3.85) == 3.9
    assert redondear(3.849) == 3.8
    assert redondear(2.95) == 3.0


@pytest.mark.parametrize("metrica,nivel", [(0, "N1"), (49.9, "N1"), (50, "N2"), (80, "N3"), (99.9, "N3"), (100, "N4")])
def test_nivel_objetivo_por_metrica(rubrica_valida, metrica, nivel):
    rub = RubricaSchema.model_validate(rubrica_valida)
    pruebas = next(c for c in rub.criterios if c.fuente == "pruebas")
    assert nivel_por_metrica(pruebas, metrica) == nivel
