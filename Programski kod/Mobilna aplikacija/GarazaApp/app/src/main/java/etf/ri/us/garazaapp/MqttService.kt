package etf.ri.us.garazaapp

import android.app.*
import android.content.Context
import android.content.Intent
import android.os.Build
import android.os.IBinder
import android.util.Log
import androidx.core.app.NotificationCompat
import com.hivemq.client.mqtt.MqttClient
import com.hivemq.client.mqtt.datatypes.MqttQos
import com.hivemq.client.mqtt.mqtt3.Mqtt3AsyncClient
import com.hivemq.client.mqtt.mqtt3.message.publish.Mqtt3Publish
import etf.ri.us.garazaapp.data.AuthUsers
import etf.ri.us.garazaapp.model.UserEvent
import kotlinx.coroutines.*
import kotlinx.coroutines.future.await
import java.nio.ByteBuffer

class MqttService : Service(), CoroutineScope {
    private val job = SupervisorJob()
    override val coroutineContext = Dispatchers.IO + job

    private lateinit var client: Mqtt3AsyncClient

    companion object {
        private const val TAG               = "MqttService"
        private const val CHANNEL_ID       = "mqtt_service_channel"
        private const val NOTIF_ID_FORE    = 1
        private const val NOTIF_ID_MESSAGE = 2
        val history = mutableListOf<UserEvent>()

        /** Topic na kojem slušamo “alarm aktivan” */
        const val TOPIC_ACTIVE      = "garaza/alarm/aktivan"
        /** Topic na kojem šaljemo komandu “alarm off” */
        const val TOPIC_OFF         = "garaza/alarm/ugasiti"

        /** Intent-action za dugme u notifikaciji */
        private const val ACTION_ALARM_OFF = "etf.ri.us.garazaapp.ACTION_ALARM_OFF"
        /** Intent-action za publish iz UI-ja */
        const val ACTION_PUBLISH     = "etf.ri.us.garazaapp.ACTION_PUBLISH"
        const val EXTRA_TOPIC        = "topic"
        const val EXTRA_MESSAGE      = "message"
    }

    override fun onCreate() {
        super.onCreate()
        createNotificationChannel()
        startForeground(NOTIF_ID_FORE, buildForegroundNotification())

        client = MqttClient.builder()
            .useMqttVersion3()
            .identifier("android-client-${System.currentTimeMillis()}")
            .serverHost("broker.hivemq.com")
            .serverPort(1883)
            .automaticReconnectWithDefaultConfig()
            .buildAsync()

        launch { connectAndSubscribe() }
    }

    private fun buildForegroundNotification(): Notification {
        val pi = PendingIntent.getActivity(
            this, 0,
            Intent(this, MainActivity::class.java),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
        )
        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle("MQTT Service")
            .setContentText("Održava vezu…")
            .setSmallIcon(android.R.drawable.ic_dialog_info)
            .setContentIntent(pi)
            .build()
    }

    private fun createNotificationChannel() {
        val mgr = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            mgr.createNotificationChannel(
                NotificationChannel(
                    CHANNEL_ID,
                    "MQTT Background",
                    NotificationManager.IMPORTANCE_HIGH
                ).apply { description = "Održava MQTT konekciju"
                    enableVibration(true)
                    enableLights(true)
                    vibrationPattern = longArrayOf(0, 500, 250, 500)}
            )
        }
    }

    /** Spoj i subscribe na alarm-active topic */
    private suspend fun connectAndSubscribe() {
        try {
            Log.d(TAG, "Connecting to broker…")
            client.connect().await()
            Log.d(TAG, "Connected")
            client.subscribeWith()
                .topicFilter(TOPIC_ACTIVE)
                .qos(MqttQos.AT_LEAST_ONCE)
                .callback(this::onMessage)
                .send()
                .await()
            Log.d(TAG, "Subscribed to $TOPIC_ACTIVE")

            client.subscribeWith()
                .topicFilter("garaza/vrata/user")
                .qos(MqttQos.AT_LEAST_ONCE)
                .callback(this::onUserMessage)
                .send()
                .await()
            Log.d(TAG, "Subscribed to garaza/vrata/user")

        } catch (e: Exception) {
            Log.e(TAG, "MQTT error", e)
        }
    }

    /** Dolazna poruka sa alarma */
    private fun onMessage(pub: Mqtt3Publish) {
        val buf: ByteBuffer = pub.payload.get().duplicate()
        val bytes = ByteArray(buf.remaining()).also { buf.get(it) }
        val message = String(bytes, Charsets.UTF_8)
        Log.d(TAG, "Message arrived: $message")
        showNotification(message)
    }

    /** Prikaz notifikacije + akcijsko dugme “Ugaši alarm” */
    private fun showNotification(message: String) {
        // akcija za gašenje
        val offIntent = Intent(this, MqttService::class.java)
            .setAction(ACTION_ALARM_OFF)
        val offPI = PendingIntent.getService(
            this, 0, offIntent,
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
        )
        val fullScreenIntent = Intent(this, MainActivity::class.java)
        val fullScreenPI = PendingIntent.getActivity(
            this, 1, fullScreenIntent,
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
        )

        val notif = NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle("Alarm aktivan!")
            .setContentText("Alarmni sistem je aktiviran zbog pokušaja neovlaštenog pristupa.")
            .setSmallIcon(android.R.drawable.ic_dialog_alert)
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setDefaults(NotificationCompat.DEFAULT_ALL)
            .setVibrate(longArrayOf(0, 500, 250, 500))
            .setFullScreenIntent(fullScreenPI, true)  // 💥 iskače preko lock screena ako sistem to dozvoli
            .addAction(android.R.drawable.ic_media_pause, "Ugasi alarm", offPI)
            .setAutoCancel(true)
            .build()


        (getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager)
            .notify(NOTIF_ID_MESSAGE, notif)
    }

    /** Obrada klikova iz notifikacije ili UI-ja */
    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        intent?.action?.let { action ->
            when (action) {
                ACTION_ALARM_OFF -> {
                    // dugme iz notifikacije
                    launch { publish(TOPIC_OFF, "alarm_off") }
                }
                ACTION_PUBLISH -> {
                    // dugmad iz MainActivity
                    val topic = intent.getStringExtra(EXTRA_TOPIC) ?: return@let
                    val msg   = intent.getStringExtra(EXTRA_MESSAGE) ?: return@let
                    launch { publish(topic, msg) }
                }
            }
        }
        return START_STICKY
    }

    /** Publish helper unutar servisa */
    private suspend fun publish(topic: String, message: String) {
        try {
            Log.d(TAG, "Publishing to '$topic': $message")
            client.publishWith()
                .topic(topic)
                .qos(MqttQos.AT_LEAST_ONCE)
                .payload(message.toByteArray())
                .send()
                .await()
            Log.d(TAG, "PUBLISH OK")
        } catch (e: Exception) {
            Log.e(TAG, "PUBLISH ERROR", e)
        }
    }

    override fun onDestroy() {
        super.onDestroy()
        job.cancel()
        runBlocking {
            try { client.disconnect().await() } catch (_: Exception) {}
        }
    }

    private fun onUserMessage(pub: Mqtt3Publish) {
        val buf: ByteBuffer = pub.payload.get().duplicate()
        val bytes = ByteArray(buf.remaining()).also { buf.get(it) }
        val rfid = String(bytes, Charsets.UTF_8).trim()

        val user = AuthUsers.getUsers().find { it.rfid == rfid }
        val event = if (user != null && !(user.ime == "none" && user.prezime == "none")) {
            UserEvent(rfid, user.ime, user.prezime, viaPin = false)
        } else {
            UserEvent(rfid, "PIN", "", viaPin = true)
        }

        Log.d(TAG, "User event: $event")

        history.add(0, event) // newest first
    }


    override fun onBind(intent: Intent?): IBinder? = null
}
