package com.earshot.companion

import android.os.Handler
import android.os.Looper
import org.java_websocket.WebSocket
import org.java_websocket.client.WebSocketClient
import org.java_websocket.handshake.ClientHandshake
import org.java_websocket.handshake.ServerHandshake
import org.java_websocket.server.WebSocketServer
import java.net.InetSocketAddress
import java.net.URI

/** Callbacks from a transport. They arrive on network threads. */
interface TransportListener {
    /** A text frame arrived. [reply] sends a frame back to the same peer. */
    fun onText(text: String, reply: (String) -> Unit)
    fun onPeers(count: Int, note: String)
    fun onState(state: String, address: String)
}

/** One way of carrying bridge messages: the phone-hosted server or the laptop relay client. */
interface Transport {
    fun start()
    fun sendToAll(text: String)
    /** Blocks briefly; call off the main thread. */
    fun shutdown()
}

/** Phone hosts a WebSocket server; the glasses app (or a test client) connects to it. */
class LocalServer(
    private val host: String,
    private val port: Int,
    private val listener: TransportListener,
) : Transport {
    private val wsUrl = "ws://$host:$port"

    private val server: WebSocketServer = object : WebSocketServer(InetSocketAddress(host, port)) {
        override fun onStart() = listener.onState("listening", wsUrl)

        override fun onOpen(conn: WebSocket, handshake: ClientHandshake) {
            val origin = handshake.getFieldValue("Origin").ifEmpty { "none" }
            listener.onPeers(openCount(null), "connected ${conn.remoteSocketAddress} path=${handshake.resourceDescriptor} origin=$origin")
        }

        override fun onClose(conn: WebSocket, code: Int, reason: String?, remote: Boolean) {
            listener.onPeers(openCount(conn), "disconnected ${conn.remoteSocketAddress} code=$code ${reason.orEmpty()}")
        }

        override fun onMessage(conn: WebSocket, message: String) {
            listener.onText(message) { out -> if (conn.isOpen) conn.send(out) }
        }

        override fun onError(conn: WebSocket?, ex: Exception) {
            if (conn == null) listener.onState("error: ${ex.message ?: ex.javaClass.simpleName}", wsUrl)
            else BridgeState.log("ERR", "client ${conn.remoteSocketAddress}: ${ex.message}")
        }
    }.apply {
        isReuseAddr = true
        connectionLostTimeout = 30 // seconds; dead clients are dropped
    }

    private fun openCount(closing: WebSocket?): Int = server.connections.count { it.isOpen && it !== closing }

    override fun start() {
        listener.onState("starting", wsUrl)
        server.start()
    }

    override fun sendToAll(text: String) = server.broadcast(text)

    override fun shutdown() {
        try { server.stop(500) } catch (_: Exception) {}
    }
}

/** Phone connects out to a relay on a laptop (tools/relay.mjs), which forwards to and from the glasses app. */
class RelayClient(
    private val url: String,
    private val listener: TransportListener,
) : Transport {
    private val main = Handler(Looper.getMainLooper())
    @Volatile private var stopped = false
    @Volatile private var client: WebSocketClient? = null

    override fun start() = connect()

    private fun connect() {
        if (stopped) return
        listener.onState("connecting", url)
        val uri = try { URI(url) } catch (e: Exception) {
            listener.onState("error: bad relay URL", url); return
        }
        val c = object : WebSocketClient(uri) {
            override fun onOpen(handshakedata: ServerHandshake?) {
                listener.onState("connected to relay", url)
                listener.onPeers(1, "relay connected")
                send(org.json.JSONObject().put("v", Protocol.VERSION).put("type", "hello")
                    .put("role", "phone").put("app", "earshot-companion").toString())
            }
            override fun onMessage(message: String) {
                listener.onText(message) { out -> if (isOpen) send(out) }
            }
            override fun onClose(code: Int, reason: String?, remote: Boolean) {
                listener.onPeers(0, "relay closed code=$code ${reason.orEmpty()}")
                if (!stopped) {
                    listener.onState("reconnecting", url)
                    main.postDelayed({ connect() }, 2000)
                }
            }
            override fun onError(ex: Exception) {
                BridgeState.log("ERR", "relay: ${ex.message ?: ex.javaClass.simpleName}")
            }
        }
        c.connectionLostTimeout = 30
        client = c
        c.connect()
    }

    override fun sendToAll(text: String) {
        client?.takeIf { it.isOpen }?.send(text)
    }

    override fun shutdown() {
        stopped = true
        main.removeCallbacksAndMessages(null)
        try { client?.closeBlocking() } catch (_: Exception) {}
    }
}
