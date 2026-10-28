import uuid
from typing import Any
import graphviz

import streamlit as st
from langchain_core.runnables import RunnableConfig
from langgraph.types import Command

from escape_graph import ROOMS, build_escape_graph, initial_state


st.set_page_config(
    page_title="Escape Room con LangGraph",
    page_icon="🔐",
    layout="wide",
)

APP_VERSION = "escape-room-v2"

def draw_game_graph(
    graph: Any,
    state: dict[str, Any],
    pending: dict[str, Any] | None,
) -> graphviz.Digraph:
    diagram = graphviz.Digraph()

    diagram.attr(
        rankdir="TB",
        bgcolor="transparent",
        nodesep="0.25",
        ranksep="0.4",
    )

    diagram.attr(
        "node",
        shape="box",
        style="rounded,filled",
        fontname="Arial",
        fontsize="11",
        margin="0.12,0.08",
    )

    diagram.attr(
        "edge",
        fontname="Arial",
        fontsize="9",
        color="#94A3B8",
        arrowsize="0.7",
    )

    labels = {
        "__start__": "INICIO",
        "read_clue": "Mostrar acertijo",
        "wait_for_answer": "Esperar respuesta",
        "check_answer": "Validar respuesta",
        "retry": "Dar ayuda",
        "next_room": "Siguiente sala",
        "final_approval": "Pedir aprobación",
        "escape": "Victoria",
        "game_over": "Fin de partida",
        "__end__": "FIN",
    }

    # El historial contiene los nombres de los nodos completados.
    visited = {
        event.split(":", 1)[0].split(" →", 1)[0].strip()
        for event in state["history"]
    }

    visited.add("__start__")

    active_node = None

    if pending:
        active_node = (
            "wait_for_answer"
            if pending["kind"] == "answer"
            else "final_approval"
        )

    finished = state["status"] in {"escaped", "game_over"}

    if finished:
        visited.add("__end__")

    # La topología procede del grafo real de LangGraph.
    topology = graph.get_graph()

    for node_id in topology.nodes:
        fill = "#F1F5F9"
        border = "#CBD5E1"
        text = "#334155"
        penwidth = "1"

        if node_id in visited:
            fill = "#DCFCE7"
            border = "#22C55E"

        if node_id == active_node:
            fill = "#FEF3C7"
            border = "#F59E0B"
            penwidth = "3"

        if finished and node_id == "__end__":
            fill = "#DBEAFE"
            border = "#3B82F6"
            penwidth = "3"

        label = labels.get(node_id, node_id)

        if node_id == active_node:
            label += "\nESPERANDO ENTRADA"

        diagram.node(
            node_id,
            label=label,
            fillcolor=fill,
            color=border,
            fontcolor=text,
            penwidth=penwidth,
        )

    edge_labels = {
        ("check_answer", "retry"): "Fallo: quedan intentos",
        ("check_answer", "game_over"): "Sin intentos",
        ("check_answer", "next_room"): "Acierto: quedan salas",
        ("check_answer", "final_approval"): "Última sala resuelta",
        ("final_approval", "escape"): "Aprobar",
        ("final_approval", "game_over"): "Rechazar",
    }

    for edge in topology.edges:
        diagram.edge(
            edge.source,
            edge.target,
            label=edge_labels.get(
                (edge.source, edge.target),
                "",
            ),
            style="dashed" if edge.conditional else "solid",
        )

    return diagram


def execute_graph(graph_input: Any) -> None:
    graph = st.session_state.escape_graph
    config: RunnableConfig = st.session_state.graph_config

    result = graph.invoke(
        graph_input,
        config=config,
    )

    snapshot = graph.get_state(config)

    st.session_state.graph_state = dict(snapshot.values)

    interruptions = result.get("__interrupt__", ())

    st.session_state.pending_interrupt = (
        interruptions[0].value if interruptions else None
    )


def reset_game() -> None:
    # Cada sesión conserva su propio grafo y checkpointer.
    st.session_state.escape_graph = build_escape_graph()
    
    
    # 👇Comprobación 
    if st.session_state.escape_graph is None:
        raise RuntimeError(
            "build_escape_graph() ha devuelto None. "
            "Revisa el return del final de escape_graph.py."
        )
        

    config: RunnableConfig = {
        "configurable": {
            "thread_id": str(uuid.uuid4()),
        },
        "recursion_limit": 100,
    }

    st.session_state.graph_config = config
    st.session_state.pending_interrupt = None
    st.session_state.celebrated = False

    # Arranca y espera la primera respuesta del jugador.
    execute_graph(initial_state())

    st.session_state.game_version = APP_VERSION


if st.session_state.get("game_version") != APP_VERSION:
    reset_game()


st.title("🔐 Escape Room con LangGraph")
st.caption(
    "Un grafo que decide, repite, espera respuestas "
    "y solicita aprobación humana."
)


with st.sidebar:
    st.header("Panel de control")

    if st.button("🔄 Reiniciar partida", use_container_width=True):
        reset_game()
        st.rerun()

    state = st.session_state.graph_state
    pending = st.session_state.pending_interrupt

    st.metric(
        "Sala actual",
        f"{state['room']} / {len(ROOMS)}",
    )

    st.metric(
        "Intentos usados en esta sala",
        f"{state['attempts']} / {state['max_attempts']}",
    )

    st.metric(
        "Salas resueltas",
        len(state["solved_rooms"]),
    )

    st.progress(
        len(state["solved_rooms"]) / len(ROOMS),
        text="Acertijos resueltos",
    )

    st.caption("Último validador utilizado")
    st.write(state["validator"])

    if pending:
        st.warning(f"Grafo pausado: {pending['kind']}")
    else:
        st.info(f"Estado: {state['status']}")

    with st.expander("Ver estado completo"):
        st.json(state)

    with st.expander("Ver identificador de partida"):
        st.code(
            st.session_state.graph_config["configurable"]["thread_id"]
        )


state = st.session_state.graph_state
pending = st.session_state.pending_interrupt

game_column, debug_column = st.columns([3, 2])


with game_column:
    if state["status"] == "escaped":
        st.success(state["feedback"])

        if not st.session_state.celebrated:
            st.balloons()
            st.session_state.celebrated = True

        st.write(
            "Has resuelto las tres salas "
            "y obtenido la aprobación final."
        )

    elif state["status"] == "game_over":
        st.error("Partida terminada")
        st.write(state["feedback"])
        st.info("Puedes reiniciar desde el panel lateral.")

    elif pending and pending["kind"] == "approval":
        st.subheader("🚪 La puerta final")
        st.success("¡Has resuelto todos los acertijos!")
        st.warning("El grafo espera la decisión del supervisor.")

        st.write(pending["question"])

        st.caption(
            "En la masterclass, otra persona puede actuar "
            "como supervisora y tomar esta decisión."
        )

        approve_column, reject_column = st.columns(2)

        if approve_column.button(
            "✅ Aprobar apertura",
            use_container_width=True,
        ):
            execute_graph(Command(resume=True))
            st.rerun()

        if reject_column.button(
            "❌ Rechazar apertura",
            use_container_width=True,
        ):
            execute_graph(Command(resume=False))
            st.rerun()

    elif pending and pending["kind"] == "answer":
        room = ROOMS[state["room"]]

        st.subheader(
            f"Sala {state['room']}: {room['title']}"
        )

        st.info(state["clue"])

        if state["feedback"]:
            if state["attempts"] == 0:
                st.success(state["feedback"])
            else:
                st.warning(state["feedback"])

        # La clave distingue formularios de salas y partidas diferentes.
        form_key = (
            f"answer_form_"
            f"{st.session_state.graph_config['configurable']['thread_id']}_"
            f"{state['room']}"
        )

        with st.form(form_key, clear_on_submit=True):
            answer = st.text_input(
                "Tu respuesta",
                placeholder="Escribe tu solución...",
                max_chars=300,
            )

            submitted = st.form_submit_button(
                "🔎 Comprobar respuesta",
                use_container_width=True,
            )

        if submitted:
            if not answer.strip():
                st.warning(
                    "Escribe una respuesta antes de continuar."
                )
            else:
                with st.spinner(
                    "Validando y ejecutando el grafo..."
                ):
                    execute_graph(
                        Command(resume=answer.strip())
                    )

                st.rerun()

    else:
        st.error(
            "No hay una pausa activa. "
            "Reinicia la partida desde el panel lateral."
        )


with debug_column:
    st.subheader("🧭 Qué está haciendo el grafo")

    diagram_tab, history_tab = st.tabs(
        ["Diagrama", "Historial"]
    )

    with diagram_tab:
        diagram = draw_game_graph(
            st.session_state.escape_graph,
            state,
            pending,
        )

        st.graphviz_chart(diagram)

        st.caption(
            "🟩 Visitado · 🟨 Esperando entrada · "
            "⬜ No visitado · 🟦 Ejecución finalizada"
        )

        st.caption(
            "Los colores resumen esta partida: un nodo verde "
            "puede haberse ejecutado varias veces. "
            "Las flechas muestran los caminos posibles, "
            "no un registro de las transiciones realizadas."
        )

        if pending:
            if pending["kind"] == "answer":
                st.info(
                    "El grafo está pausado hasta que "
                    "el jugador envíe una respuesta."
                )
            else:
                st.info(
                    "El grafo está pausado hasta recibir "
                    "la aprobación o el rechazo del supervisor."
                )

        elif state["status"] == "escaped":
            st.success("El grafo ha terminado con victoria.")

        elif state["status"] == "game_over":
            st.warning("El grafo ha terminado sin abrir la puerta.")

    with history_tab:
        st.caption(
            "Orden de los nodos completados durante la partida."
        )

        for index, event in enumerate(
            state["history"],
            start=1,
        ):
            st.text(f"{index}. {event}")

        if pending:
            waiting_node = (
                "wait_for_answer"
                if pending["kind"] == "answer"
                else "final_approval"
            )

            st.warning(
                f"⏸️ {waiting_node}: esperando entrada humana"
            )

        with st.expander("Ver código Mermaid"):
            st.code(
                st.session_state.escape_graph
                .get_graph()
                .draw_mermaid(),
                language="mermaid",
            )