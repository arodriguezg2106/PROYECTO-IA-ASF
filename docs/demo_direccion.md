# Demostración de viabilidad para Dirección

## Objetivo

Mostrar, desde una sola computadora y con documentos completamente sintéticos,
que Revisor-CRF puede localizar discrepancias, evitar falsos positivos conocidos,
declarar sus límites y apoyar la revisión editorial sin modificar el documento
original.

Esta demostración **no es un despliegue productivo**. No usa SQL Server, IIS,
servicios externos ni documentos institucionales. La IA contextual permanece
fuera del recorrido obligatorio y sólo podrá añadirse después como módulo
experimental claramente separado.

## Preparación

Desde PowerShell, en la raíz del repositorio:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\scripts\start_local_demo.ps1 -Editorial
```

Antes de abrir la web, el script genera cuatro DOCX bajo
`data/demo_direccion/` y ejecuta una verificación automática. El resultado queda
en `results/demo/direction-preflight.json`; ambos directorios están ignorados por
Git.

## Recorrido sugerido (10–15 minutos)

1. **Contexto y límites — 1 minuto.** Explicar que todo se ejecuta localmente,
   que los datos son inventados y que el original nunca se modifica.
2. **Suma incorrecta — 3 minutos.** Cargar `01_suma_incorrecta.docx`. Mostrar
   que 100 + 50 no coincide con el total declarado de 200, así como la ubicación,
   suma calculada y diferencia.
3. **Control de falsos positivos — 2 minutos.** Cargar
   `02_suma_correcta_compleja.docx`. La tabla tiene título combinado y dos
   columnas monetarias; ambas sumas son correctas y no deben producir alerta ni
   limitación de total.
4. **Transparencia — 2 minutos.** Cargar `03_operacion_no_evaluable.docx`.
   Pesos y número de obras no se deben sumar. Mostrar “Operaciones no evaluadas”
   y recalcar que no se trata como error ni genera comentario de Word.
5. **Revisión editorial — 3 minutos.** Cargar `04_revision_editorial.docx`.
   Mostrar las reglas ASF sobre `y/o`, porcentaje separado y formas no
   recomendadas. Las propuestas requieren decisión humana y no autocorrigen.
6. **Entregables — 2 minutos.** Abrir el HTML y descargar JSON y DOCX comentado.
7. **Cierre — 1 minuto.** Solicitar autorización para una evaluación controlada
   y, sólo después, iniciar seguridad DAST, infraestructura y piloto.

Use **“Revisar otro documento”** entre casos. Para detener la aplicación,
presione `Ctrl+C` en la terminal.

## Criterios objetivos de la demostración

- Los cuatro casos superan el preflight automático.
- La discrepancia comprobable produce exactamente una alerta de total.
- La tabla compleja correcta evalúa dos totales sin alertas ni limitaciones.
- Las unidades incompatibles producen una limitación neutral, no una alerta.
- El caso editorial detecta las tres familias de reglas previstas.
- Los cuatro trabajos terminan y permiten descargar sus entregables.
- Ningún texto o decisión modifica los DOCX originales.

## Plan de contingencia

La demostración obligatoria no depende de Ollama. Si posteriormente se habilita
un asistente experimental, sus resultados se mostrarán en una sección separada,
con límite de sugerencias y decisión humana. Una falla de ese proveedor no podrá
interrumpir el resultado determinístico.

## Asistente experimental de alta cobertura

Gemma 3 12B puede añadirse a la misma demostración con:

```powershell
.\scripts\start_local_demo.ps1 -Editorial -ExperimentalAI
```

Ollama debe estar disponible mediante `127.0.0.1` con el modelo `gemma3:12b`.
También puede utilizarse un túnel seguro que exponga el servidor remoto como un
puerto loopback local; el navegador nunca se conecta directamente con Ollama.

Este modo reproduce el prompt de alta cobertura evaluado en Colab. En el banco
difícil obtuvo precisión `0.375`, exhaustividad `0.75`, exactitud `0.40` y acuerdo
`1.00`. Por ello:

- permanece rechazado para uso institucional;
- por defecto sólo procesa los cuatro DOCX sintéticos generados en esa ejecución;
- muestra como máximo cinco sugerencias;
- identifica todas sus propuestas como experimentales;
- permite confirmarlas o marcarlas como falso positivo;
- no genera comentarios de Word ni autocorrige;
- si Ollama no responde o su digest no coincide, el resultado determinístico
  termina y el proveedor aparece como `partial`.

Para ejecutar sólo la demo estable, omita `-ExperimentalAI`.

Para evaluar deliberadamente la IA sobre cualquier DOCX autorizado durante
una sesión local, use:

```powershell
.\scripts\start_local_demo.ps1 -Editorial -ExperimentalAI `
  -ExperimentalAIAllDocuments
```

Esta apertura no cambia el estado rechazado del modelo ni sus métricas. Todas
las propuestas continúan marcadas como experimentales, limitadas a cinco y
sujetas a decisión humana. El texto se envía únicamente al Ollama configurado
en loopback; no se envía a Colab ni a una API externa.

## Evaluación desde otra computadora de la misma red

Para que otra persona recorra la interfaz desde su navegador, inicie una demo
LAN temporal:

```powershell
.\scripts\start_local_demo.ps1 -Editorial -LanDemo
```

El script mostrará una dirección privada, por ejemplo
`http://192.168.1.25:8000`, y un código temporal. Comparta ambos únicamente con
la persona evaluadora dentro de la misma red. Cada navegador recibe una sesión
independiente y sólo puede consultar sus propios trabajos.

Si la detección automática elige una interfaz incorrecta, indique la dirección
IPv4 del equipo anfitrión:

```powershell
.\scripts\start_local_demo.ps1 -Editorial -LanDemo -LanAddress 192.168.1.25
```

Puede añadir `-ExperimentalAI` para los casos sintéticos autorizados. El puerto
no debe redirigirse en el router ni publicarse en Internet. Al presionar
`Ctrl+C` terminan el servidor y las sesiones temporales. Si Windows solicita
permiso de Firewall, autorice exclusivamente redes privadas.

Para que la persona evaluadora pruebe la IA con cualquier DOCX autorizado:

```powershell
.\scripts\start_local_demo.ps1 -Editorial -ExperimentalAI `
  -ExperimentalAIAllDocuments -LanDemo
```
