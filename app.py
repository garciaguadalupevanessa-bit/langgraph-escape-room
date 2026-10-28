import uuid
from typing import Any

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
    st.subheader("🧭 Recorrido del grafo")

    st.caption(
        "Los nodos completados registran su paso. "
        "La pausa activa aparece al final."
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

    with st.expander("Ver código Mermaid del grafo"):
        st.code(
            st.session_state.escape_graph
            .get_graph()
            .draw_mermaid(),
            language="mermaid",
        )