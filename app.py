import io
import os
from fpdf import FPDF
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import streamlit as st

st.set_page_config(layout="wide", page_title="Evaluación de TC por Subestación")

col1, col2, col3 = st.columns([1, 2, 1])
with col2:
  if os.path.exists("logo_saesa.png"):
    st.image("logo_saesa.png")

st.markdown(
    """
<style>
    .bg-blue { background-color: #ddebf7; padding: 10px; border-radius: 5px; margin-bottom: 10px;}
</style>
""",
    unsafe_allow_html=True,
)


# 1. GENERADOR DE PLANTILLA EXCEL
def generar_plantilla():
  output = io.BytesIO()
  with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
    df_plantilla = pd.DataFrame({
        "Subestacion": ["ALTAMIRANO 110 kV B1"] * 2 + ["S/E Valdivia"] * 2,
        "Ipsc_A": [48.864] * 2 + [12500.0] * 2,
        "Relacion_XR": [5.868] * 2 + [10.5] * 2,
        "Isr_Perm_A": [5] * 4,
        "ALFn": [20] * 4,
        "Res_20_Ohm_km": [3.76] * 2 + [3.3] * 2,
        "Largo_Perm_m": [59.7] * 2 + [55.0] * 2,
        "Burden_Rele_Perm_VA": [0.5] * 4,
        "Metodo_RCT": ["0.5 * Rb"] * 2 + ["Prueba FAT"] * 2,
        "Delta_Phi_min": [6] * 4,
        "t_al_s": [0.005] * 4,
        "N_TAP": [1, 2, 1, 2],
        "TAP": [400, 200, 1200, 800],
        "Burden": [30, 15, 50, 30],
        "RCT_FAT": [0, 0, 1.25, 0.85],
    })
    df_plantilla.to_excel(writer, sheet_name="Evaluacion_TC", index=False)
  return output.getvalue()


# 2. CÁLCULO POR SUBESTACIÓN
def evaluar_subestacion(df_sub):
  f_fija = 50.0
  w_comun = 2 * np.pi * f_fija
  coef_temp = 0.00393

  d_gen = df_sub.iloc[0]
  ipsc = float(d_gen["Ipsc_A"])
  relacion_xr = float(d_gen["Relacion_XR"])
  isr_perm = float(d_gen["Isr_Perm_A"])
  alfn = float(d_gen["ALFn"])
  res_20 = float(d_gen["Res_20_Ohm_km"])
  largo_perm = float(d_gen["Largo_Perm_m"])
  burden_rele_perm = float(d_gen["Burden_Rele_Perm_VA"])
  metodo_rct = str(d_gen["Metodo_RCT"]).strip()
  delta_phi = float(d_gen["Delta_Phi_min"])
  t_al = float(d_gen["t_al_s"])

  tp_comun = relacion_xr / w_comun if w_comun != 0 else 0
  r_rele_perm = burden_rele_perm / (isr_perm**2) if isr_perm != 0 else 0
  rc_75_perm = res_20 * (largo_perm / 1000) * 2 * (1 + coef_temp * (75 - 20))
  rb_prima_perm = rc_75_perm + r_rele_perm

  # Permanente
  res_perm = []
  for _, row in df_sub.iterrows():
    n = int(row["N_TAP"])
    tap = float(row["TAP"])
    burden = float(row["Burden"])
    rct_fat_val = float(row["RCT_FAT"])

    rb = burden / (isr_perm**2) if isr_perm != 0 else 0
    rct_calc = rb * 0.5 if metodo_rct == "0.5 * Rb" else rct_fat_val

    rs_calc = rb_prima_perm + rct_calc
    alf_calc = alfn * (rb + rct_calc) / rs_calc if rs_calc != 0 else 0
    kssc = ipsc / tap if tap != 0 else 0
    estado = "Cumple" if alf_calc >= kssc else "No Cumple"

    res_perm.append(
        [n, tap, burden, rct_calc, rb, rs_calc, alf_calc, kssc, estado]
    )

  df_perm = pd.DataFrame(
      res_perm,
      columns=["N° TAP", "TAP", "Burden", "RCT", "Rb", "Rs", "ALF'", "Kssc", "Estado"],
  )

  # Transitorio
  ts = 3438 / (2 * np.pi * f_fija * delta_phi) if delta_phi != 0 else 0
  y_val, x_val = 0.0, 0.0
  if ts != 0 and tp_comun != ts:
    factor_exp = np.exp(t_al / ts)
    factor_trig = (w_comun * ts * np.cos(w_comun * t_al)) - np.sin(
        w_comun * t_al
    )
    y_val = (w_comun * ts) - (factor_exp * factor_trig)

    term1 = 1 / (tp_comun - ts)
    term2 = (
        tp_comun
        * (1 + (w_comun * ts) ** 2)
        * np.exp((t_al / ts) - (t_al / tp_comun))
    )
    term3 = ts * (1 + (w_comun**2) * ts * tp_comun)
    term4 = np.exp(t_al / ts) * (
        np.cos(w_comun * t_al) + w_comun * ts * np.sin(w_comun * t_al)
    )
    x_val = term1 * (term2 - term3) - term4

  theta_rad = np.arctan2(y_val, x_val) if x_val != 0 else 0.0
  theta_grad = np.rad2deg(theta_rad)
  phi = np.arctan(relacion_xr)
  t_tf_max = (np.pi + phi) / w_comun if w_comun != 0 else 0.0
  rango_1 = "En Rango" if t_al <= t_tf_max else "Fuera de Rango"

  ktf_simp = 0.0
  if tp_comun != ts and ts != 0:
    term_a = (w_comun * ts * tp_comun) / (tp_comun - ts)
    term_b = np.cos(theta_rad) * (np.exp(-t_al / tp_comun) - np.exp(-t_al / ts))
    term_c = np.sin(theta_rad) * np.exp(-t_al / ts)
    term_d = np.sin((w_comun * t_al) + theta_rad)
    ktf_simp = (term_a * term_b) + term_c - term_d

  res_trans = []
  for idx, row in df_perm.iterrows():
    rb_mas_rct = row["Rb"] + row["RCT"]
    rb_prim_mas_rct = rb_prima_perm + row["RCT"]
    ealf = isr_perm * alfn * rb_mas_rct

    tap_val = row["TAP"]
    ereq = (
        (ktf_simp * ipsc * isr_perm / tap_val) * rb_prim_mas_rct
        if tap_val != 0
        else 0.0
    )
    estado_trans = "Cumple" if ealf >= ereq else "No Cumple"

    res_trans.append([
        row["N° TAP"],
        tap_val,
        row["Burden"],
        row["RCT"],
        row["Rb"],
        rb_prima_perm,
        rb_mas_rct,
        rb_prim_mas_rct,
        ealf,
        ereq,
        estado_trans,
    ])

  df_trans = pd.DataFrame(
      res_trans,
      columns=[
          "N° TAP",
          "TAP",
          "Burden",
          "RCT",
          "Rb",
          "Rb'",
          "Rb+Rct",
          "Rb'+Rct",
          "EALF",
          "Ereq",
          "Estado",
      ],
  )

  estado_gen_perm = (
      "Cumple" if all(df_perm["Estado"] == "Cumple") else "No Cumple"
  )
  estado_gen_trans = (
      "Cumple" if all(df_trans["Estado"] == "Cumple") else "No Cumple"
  )

  return {
      "d_gen": d_gen,
      "df_perm": df_perm,
      "df_trans": df_trans,
      "rc_75_perm": rc_75_perm,
      "rb_prima_perm": rb_prima_perm,
      "ts": ts,
      "w_comun": w_comun,
      "y_val": y_val,
      "x_val": x_val,
      "theta_rad": theta_rad,
      "theta_grad": theta_grad,
      "phi": phi,
      "t_tf_max": t_tf_max,
      "rango_1": rango_1,
      "ktf_simp": ktf_simp,
      "tp_comun": tp_comun,
      "f_fija": f_fija,
      "r_rele_perm": r_rele_perm,
      "estado_gen_perm": estado_gen_perm,
      "estado_gen_trans": estado_gen_trans,
  }


# 3. GENERADORES DE INFORMES
def sanitize_text(text):
  text = (
      str(text)
      .replace("Ω", "Ohm")
      .replace("°", "grados")
      .replace("Δ", "Delta")
      .replace("φ", "phi")
      .replace("θ", "theta")
      .replace("ω", "w")
      .replace("²", "2")
      .replace("—", "-")
      .replace("–", "-")
  )
  return text.encode("latin-1", "replace").decode("latin-1")


def generar_excel_global(resultados, inc_perm, inc_trans):
  output = io.BytesIO()
  with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
    # HOJA 1: BASE DE DATOS POWER BI (TABULAR POR TAP)
    db_rows = []
    for sub, d in resultados.items():
      d_gen = d["d_gen"]
      df_p = d["df_perm"]
      df_t = d["df_trans"]
      for i in range(len(df_p)):
        row_p = df_p.iloc[i]
        row_t = df_t.iloc[i]
        db_rows.append({
            "Subestacion": sub,
            "Ipsc_A": d_gen["Ipsc_A"],
            "Relacion_XR": d_gen["Relacion_XR"],
            "Isr_Perm_A": d_gen["Isr_Perm_A"],
            "ALFn": d_gen["ALFn"],
            "Res_20_Ohm_km": d_gen["Res_20_Ohm_km"],
            "Largo_Perm_m": d_gen["Largo_Perm_m"],
            "Burden_Rele_Perm_VA": d_gen["Burden_Rele_Perm_VA"],
            "Metodo_RCT": d_gen["Metodo_RCT"],
            "N_TAP": int(row_p["N° TAP"]),
            "TAP_A": float(row_p["TAP"]),
            "Burden_VA": float(row_p["Burden"]),
            "RCT_Ohm": float(row_p["RCT"]),
            "Rb_Ohm": float(row_p["Rb"]),
            "Rs_Ohm": float(row_p["Rs"]),
            "ALF_prima": float(row_p["ALF'"]),
            "Kssc": float(row_p["Kssc"]),
            "Estado_Permanente": row_p["Estado"],
            "EALF": float(row_t["EALF"]),
            "Ereq": float(row_t["Ereq"]),
            "Estado_Transitorio": row_t["Estado"],
            "Estado_Final_TAP": (
                "Cumple"
                if (
                    row_p["Estado"] == "Cumple" and row_t["Estado"] == "Cumple"
                )
                else "No Cumple"
            ),
        })
    pd.DataFrame(db_rows).to_excel(
        writer, sheet_name="Base_Datos_PowerBI", index=False
    )

    # HOJA 2: RESUMEN GLOBAL POR SUBESTACIÓN
    resumen_data = []
    for sub, d in resultados.items():
      resumen_data.append({
          "Subestación": sub,
          "Ipsc (A)": d["d_gen"]["Ipsc_A"],
          "Relación X/R": d["d_gen"]["Relacion_XR"],
          "Estado Permanente": d["estado_gen_perm"],
          "Estado Transitorio": d["estado_gen_trans"],
      })
    pd.DataFrame(resumen_data).to_excel(
        writer, sheet_name="Resumen Global", index=False
    )

    # HOJAS POR SUBESTACIÓN
    for sub, d in resultados.items():
      sheet_name = (
          sub[:31]
          .replace("/", "-")
          .replace("[", "")
          .replace("]", "")
          .replace("*", "")
      )
      start_row = 0
      d_gen = d["d_gen"]

      if inc_perm or inc_trans:
        df_com = pd.DataFrame({
            "Parámetro": [
                "Subestación",
                "Ipsc (A)",
                "Relación X/R",
                "Frecuencia (Hz)",
                "Tp (s)",
            ],
            "Valor": [
                sub,
                d_gen["Ipsc_A"],
                d_gen["Relacion_XR"],
                d["f_fija"],
                d["tp_comun"],
            ],
        })
        df_com.to_excel(
            writer, sheet_name=sheet_name, startrow=start_row, index=False
        )
        start_row += len(df_com) + 2

      if inc_perm:
        df_ent_p = pd.DataFrame({
            "Parámetro": [
                "Isr (A)",
                "ALFn",
                "Resistencia 20° (Ω/km)",
                "Largo (m)",
                "Burden relé (VA)",
                "Rrelé (Ω)",
                "RC a 75° (Ω)",
                "R'b (Ω)",
            ],
            "Valor": [
                d_gen["Isr_Perm_A"],
                d_gen["ALFn"],
                d_gen["Res_20_Ohm_km"],
                d_gen["Largo_Perm_m"],
                d_gen["Burden_Rele_Perm_VA"],
                d["r_rele_perm"],
                d["rc_75_perm"],
                d["rb_prima_perm"],
            ],
        })
        df_ent_p.to_excel(
            writer, sheet_name=sheet_name, startrow=start_row, index=False
        )
        start_row += len(df_ent_p) + 2
        d["df_perm"].to_excel(
            writer, sheet_name=sheet_name, startrow=start_row, index=False
        )
        start_row += len(d["df_perm"]) + 2

      if inc_trans:
        df_ent_t = pd.DataFrame({
            "Parámetro": [
                "Δ φ [min]",
                "t'al (s)",
                "ts (s)",
                "ω (rad/s)",
                "Y",
                "X",
                "θtf,max (rad)",
                "θtf,max (grados)",
                "φ (rad)",
                "ttf,max (s)",
                "Rango 1",
                "Ktd",
            ],
            "Valor": [
                d_gen["Delta_Phi_min"],
                d_gen["t_al_s"],
                d["ts"],
                d["w_comun"],
                d["y_val"],
                d["x_val"],
                d["theta_rad"],
                d["theta_grad"],
                d["phi"],
                d["t_tf_max"],
                d["rango_1"],
                d["ktf_simp"],
            ],
        })
        df_ent_t.to_excel(
            writer, sheet_name=sheet_name, startrow=start_row, index=False
        )
        start_row += len(df_ent_t) + 2
        d["df_trans"].to_excel(
            writer, sheet_name=sheet_name, startrow=start_row, index=False
        )

  return output.getvalue()


def generar_pdf_global(resultados, inc_perm, inc_trans):
  pdf = FPDF()
  for sub, d in resultados.items():
    pdf.add_page()
    pdf.set_font("Arial", "B", 14)
    pdf.cell(
        0,
        10,
        sanitize_text(f"Reporte de Evaluación de TC - {sub}"),
        ln=True,
        align="C",
    )
    pdf.ln(5)
    d_gen = d["d_gen"]

    def add_section(title, data_dict):
      pdf.set_font("Arial", "B", 11)
      pdf.cell(0, 8, sanitize_text(title), ln=True)
      pdf.set_font("Arial", "", 10)
      for k, v in data_dict.items():
        pdf.cell(0, 5, sanitize_text(f"{k}: {v}"), ln=True)
      pdf.ln(3)

    def add_table(df):
      pdf.set_font("Arial", "B", 7)
      ef_width = pdf.w - pdf.l_margin - pdf.r_margin
      col_width = ef_width / len(df.columns)
      row_height = 5
      for col in df.columns:
        pdf.cell(
            col_width,
            row_height,
            sanitize_text(str(col)),
            border=1,
            align="C",
        )
      pdf.ln(row_height)
      pdf.set_font("Arial", "", 7)
      for _, row in df.iterrows():
        for val in row:
          val_str = (
              f"{val:.2f}"
              if isinstance(val, float)
              else sanitize_text(str(val))
          )
          pdf.cell(col_width, row_height, val_str, border=1, align="C")
        pdf.ln(row_height)

    if inc_perm or inc_trans:
      add_section(
          "1. Datos Comunes TC",
          {
              "Subestación": sub,
              "Ipsc (A)": d_gen["Ipsc_A"],
              "Relación X/R": d_gen["Relacion_XR"],
              "Frecuencia (Hz)": d["f_fija"],
              "Tp (s)": round(d["tp_comun"], 6),
          },
      )
    if inc_perm:
      add_section(
          "2. Regimen Permanente TC",
          {
              "Isr (A)": d_gen["Isr_Perm_A"],
              "ALFn": d_gen["ALFn"],
              "Resistencia 20 (Ohm/km)": d_gen["Res_20_Ohm_km"],
              "Largo (m)": d_gen["Largo_Perm_m"],
              "Burden relé (VA)": d_gen["Burden_Rele_Perm_VA"],
              "Rrelé (Ohm)": round(d["r_rele_perm"], 6),
              "Método RCT": d_gen["Metodo_RCT"],
              "R Conductor 75 (Ohm)": round(d["rc_75_perm"], 6),
              "R'b (Ohm)": round(d["rb_prima_perm"], 6),
          },
      )
      pdf.set_font("Arial", "B", 10)
      pdf.cell(0, 8, "Tabla Permanente:", ln=True)
      add_table(d["df_perm"])
      pdf.ln(5)
    if inc_trans:
      add_section(
          "3. Regimen Transitorio TC",
          {
              "Delta phi [min]": d_gen["Delta_Phi_min"],
              "t'al (s)": d_gen["t_al_s"],
              "ts (s)": round(d["ts"], 6),
              "w (rad/s)": round(d["w_comun"], 6),
              "Y": round(d["y_val"], 6),
              "X": round(d["x_val"], 6),
              "theta_tf,max (rad)": round(d["theta_rad"], 6),
              "theta_tf,max (grados)": round(d["theta_grad"], 6),
              "phi (rad)": round(d["phi"], 6),
              "ttf,max (s)": round(d["t_tf_max"], 6),
              "Rango": d["rango_1"],
              "Ktf Simplificado (Ktd)": round(d["ktf_simp"], 6),
          },
      )
      pdf.set_font("Arial", "B", 10)
      pdf.cell(0, 8, "Tabla Transitorio:", ln=True)
      add_table(d["df_trans"])
      pdf.ln(5)

  return pdf.output(dest="S").encode("latin-1")


# 4. INTERFAZ PRINCIPAL
with st.sidebar:
  st.header("1. Plantilla de Entrada")
  st.download_button(
      "📥 Descargar Plantilla Excel",
      generar_plantilla(),
      "Plantilla_Entradas_TC.xlsx",
      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      use_container_width=True,
  )
  st.markdown("---")
  st.header("2. Cargar Evaluación")
  archivo_excel = st.file_uploader(
      "Sube el archivo Excel con tus datos", type=["xlsx"]
  )

  st.markdown("---")
  st.subheader("3. Configurar Informes")
  inc_perm = st.checkbox("Régimen Permanente", value=True)
  inc_trans = st.checkbox("Régimen Transitorio", value=True)

if archivo_excel is not None:
  try:
    df_tot = pd.read_excel(archivo_excel, sheet_name=0)
    df_tot.columns = df_tot.columns.str.strip()

    resultados_total = {}
    resumen_data = []

    for sub in df_tot["Subestacion"].unique():
      df_sub = df_tot[df_tot["Subestacion"] == sub].copy()
      res = evaluar_subestacion(df_sub)
      resultados_total[sub] = res
      resumen_data.append({
          "Subestación": sub,
          "Ipsc (A)": res["d_gen"]["Ipsc_A"],
          "Relación X/R": res["d_gen"]["Relacion_XR"],
          "Estado Permanente": res["estado_gen_perm"],
          "Estado Transitorio": res["estado_gen_trans"],
      })

    st.subheader("Resumen Global de Subestaciones Evaluadas")
    st.dataframe(
        pd.DataFrame(resumen_data), hide_index=True, use_container_width=True
    )

    total_sub = len(resultados_total)
    sat_ambos = 0
    sat_solo_perm = 0
    sat_solo_trans = 0
    sin_sat = 0

    for sub, r in resultados_total.items():
      p_ok = r["estado_gen_perm"] == "Cumple"
      t_ok = r["estado_gen_trans"] == "Cumple"
      if not p_ok and not t_ok:
        sat_ambos += 1
      elif not p_ok and t_ok:
        sat_solo_perm += 1
      elif p_ok and not t_ok:
        sat_solo_trans += 1
      else:
        sin_sat += 1

    pct_ok = (sin_sat / total_sub) * 100 if total_sub > 0 else 0
    pct_p = (sat_solo_perm / total_sub) * 100 if total_sub > 0 else 0
    pct_t = (sat_solo_trans / total_sub) * 100 if total_sub > 0 else 0
    pct_uno = (
        ((sat_solo_perm + sat_solo_trans) / total_sub) * 100 if total_sub > 0 else 0
    )
    pct_ambos = (sat_ambos / total_sub) * 100 if total_sub > 0 else 0

    st.markdown("### Estadísticas Generales de Saturación")
    col_e1, col_e2, col_e3, col_e4 = st.columns(4)
    col_e1.metric("Sin saturación", f"{pct_ok:.1f}%", f"{sin_sat} S/E")
    col_e2.metric(
        "Saturan en 1 régimen",
        f"{pct_uno:.1f}%",
        f"{sat_solo_perm + sat_solo_trans} S/E",
    )
    col_e3.metric("Saturan en ambos", f"{pct_ambos:.1f}%", f"{sat_ambos} S/E")
    col_e4.metric(
        "Total con saturación",
        f"{(100 - pct_ok):.1f}%",
        f"{total_sub - sin_sat} S/E",
    )

    col_g1, col_g2 = st.columns([1, 1])
    with col_g1:
      st.markdown("**Desglose detallado:**")
      st.write(
          f"- **Solo en Permanente:** {sat_solo_perm} S/E ({pct_p:.1f}%)"
      )
      st.write(
          f"- **Solo en Transitorio:** {sat_solo_trans} S/E ({pct_t:.1f}%)"
      )
      st.write(
          f"- **En ambos regímenes:** {sat_ambos} S/E ({pct_ambos:.1f}%)"
      )
      st.write(f"- **Cumplen todo:** {sin_sat} S/E ({pct_ok:.1f}%)")

    with col_g2:
      fig_gen, ax_gen = plt.subplots(figsize=(5, 2.8))
      cats = [
          "Sin saturar",
          "Solo Perm.",
          "Solo Trans.",
          "Ambos",
      ]
      vals = [sin_sat, sat_solo_perm, sat_solo_trans, sat_ambos]
      colors = ["#2ca02c", "#ff7f0e", "#1f77b4", "#d62728"]
      bars = ax_gen.bar(cats, vals, color=colors)
      ax_gen.set_ylabel("N° de S/E")
      ax_gen.set_title("Distribución Global de Saturación")
      for i, v in enumerate(vals):
        pct = (v / total_sub) * 100 if total_sub > 0 else 0
        ax_gen.text(
            i,
            v + 0.05,
            f"{pct:.1f}%",
            ha="center",
            va="bottom",
            fontsize=8,
        )
      st.pyplot(fig_gen)
      plt.close(fig_gen)

    st.markdown("### 📥 Descargar Informe Global (Todas las Subestaciones)")
    col_dl1, col_dl2 = st.columns(2)
    with col_dl1:
      st.download_button(
          label="📄 Descargar TODO en PDF",
          data=generar_pdf_global(resultados_total, inc_perm, inc_trans),
          file_name="Reporte_Global_TC.pdf",
          mime="application/pdf",
          use_container_width=True,
      )
    with col_dl2:
      st.download_button(
          label="📊 Descargar TODO en Excel",
          data=generar_excel_global(resultados_total, inc_perm, inc_trans),
          file_name="Reporte_Global_TC.xlsx",
          mime=(
              "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
          ),
          use_container_width=True,
      )

    st.markdown("---")

    sub_sel = st.selectbox(
        "🔍 Selecciona una subestación para ver detalles técnicos en pantalla:",
        list(resultados_total.keys()),
    )
    d = resultados_total[sub_sel]
    d_gen = d["d_gen"]

    c1, c2, c3 = st.columns(3)
    c1.metric("Ipsc (A)", f"{d_gen['Ipsc_A']}")
    c2.metric("Relación X/R", f"{d_gen['Relacion_XR']}")
    c3.metric("Método RCT", str(d_gen["Metodo_RCT"]))

    t_perm, t_trans, t_graf = st.tabs([
        "Régimen Permanente",
        "Régimen Transitorio",
        "Análisis Gráfico",
    ])
    with t_perm:
      col_m1, col_m2 = st.columns(2)
      col_m1.metric(
          "Resistencia conductor (RC) a 75° (Ω)", f"{d['rc_75_perm']:.7f}"
      )
      col_m2.metric("R'b (Ω)", f"{d['rb_prima_perm']:.7f}")
      st.dataframe(d["df_perm"], hide_index=True, use_container_width=True)
    with t_trans:
      st.dataframe(d["df_trans"], hide_index=True, use_container_width=True)

    with t_graf:
      st.markdown("### Comparación de Capacidad vs Requerimiento por TAP")
      col_p1, col_p2 = st.columns(2)

      taps_labels = [
          f"TAP {int(row['N° TAP'])}\n({int(row['TAP'])}A)"
          for _, row in d["df_perm"].iterrows()
      ]
      x = np.arange(len(taps_labels))
      width = 0.35

      with col_p1:
        fig1, ax1 = plt.subplots(figsize=(6, 4))
        ax1.bar(
            x - width / 2,
            d["df_perm"]["ALF'"],
            width,
            label="ALF' (Calculado)",
            color="#1f77b4",
        )
        ax1.bar(
            x + width / 2,
            d["df_perm"]["Kssc"],
            width,
            label="Kssc (Requerido)",
            color="#ff7f0e",
        )
        ax1.set_ylabel("Factor")
        ax1.set_title("Régimen Permanente: ALF' vs Kssc")
        ax1.set_xticks(x)
        ax1.set_xticklabels(taps_labels)
        ax1.legend()
        ax1.grid(axis="y", linestyle="--", alpha=0.6)
        st.pyplot(fig1)
        plt.close(fig1)

      with col_p2:
        fig2, ax2 = plt.subplots(figsize=(6, 4))
        ax2.bar(
            x - width / 2,
            d["df_trans"]["EALF"],
            width,
            label="EALF (Calculado)",
            color="#1f77b4",
        )
        ax2.bar(
            x + width / 2,
            d["df_trans"]["Ereq"],
            width,
            label="Ereq (Requerido)",
            color="#ff7f0e",
        )
        ax2.set_ylabel("Valor (E)")
        ax2.set_title("Régimen Transitorio: EALF vs Ereq")
        ax2.set_xticks(x)
        ax2.set_xticklabels(taps_labels)
        ax2.legend()
        ax2.grid(axis="y", linestyle="--", alpha=0.6)
        st.pyplot(fig2)
        plt.close(fig2)

    st.markdown(f"### 📥 Descargar Informe Individual ({sub_sel})")
    col_i1, col_i2 = st.columns(2)
    nombre_base = sub_sel.replace(" ", "_").replace("/", "-")
    with col_i1:
      st.download_button(
          label=f"📄 PDF - {sub_sel}",
          data=generar_pdf_global({sub_sel: d}, inc_perm, inc_trans),
          file_name=f"Reporte_{nombre_base}.pdf",
          mime="application/pdf",
          use_container_width=True,
      )
    with col_i2:
      st.download_button(
          label=f"📊 Excel - {sub_sel}",
          data=generar_excel_global({sub_sel: d}, inc_perm, inc_trans),
          file_name=f"Reporte_{nombre_base}.xlsx",
          mime=(
              "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
          ),
          use_container_width=True,
      )

  except Exception as e:
    st.error(f"Error al procesar el archivo Excel. Detalle técnico: {e}")
else:
  st.info(
      "👆 Descarga la plantilla en la barra lateral, rellénala con tus datos y"
      " súbela para procesar las subestaciones."
  )
