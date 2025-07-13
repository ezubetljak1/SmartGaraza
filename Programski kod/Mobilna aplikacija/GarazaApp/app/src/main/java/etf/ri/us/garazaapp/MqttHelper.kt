// MqttHelper.kt
package etf.ri.us.garazaapp

import android.util.Log
import com.hivemq.client.mqtt.MqttClient
import com.hivemq.client.mqtt.datatypes.MqttQos
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.coroutines.future.await
import java.nio.ByteBuffer

class MqttHelper {

    companion object {
        private const val TAG = "MqttHelper"
    }

    private val client = MqttClient.builder()
        .useMqttVersion3()
        .identifier("android-client-${System.currentTimeMillis()}")
        .serverHost("broker.hivemq.com")
        .serverPort(1883)
        .automaticReconnectWithDefaultConfig()
        .buildAsync()

    suspend fun connect() {
        withContext(Dispatchers.IO) {
            try {
                Log.d(TAG, "Pokušavam se spojiti…")
                client.connect().await()
                Log.d(TAG, "CONNECT OK")
            } catch (e: Exception) {
                Log.e(TAG, "CONNECT ERROR", e)
            }
        }
    }

    suspend fun subscribe(topic: String, onMessage: (String) -> Unit) {
        withContext(Dispatchers.IO) {
            try {
                Log.d(TAG, "Pretplaćujem se na topic '$topic'…")
                client.subscribeWith()
                    .topicFilter(topic)
                    .qos(MqttQos.AT_LEAST_ONCE)
                    .callback { publish ->
                        // copy read-only buffer into a byte array
                        val buf: ByteBuffer = publish.payload.get().duplicate()
                        val bytes = ByteArray(buf.remaining()).also { buf.get(it) }
                        val msg = String(bytes, Charsets.UTF_8)

                        Log.d(TAG, "<<< MESSAGE on '$topic': $msg")
                        onMessage(msg)
                    }
                    .send()
                    .await()
                Log.d(TAG, "SUBSCRIBE OK")
            } catch (e: Exception) {
                Log.e(TAG, "SUBSCRIBE ERROR", e)
            }
        }
    }

    suspend fun publish(topic: String, message: String) {
        withContext(Dispatchers.IO) {
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
    }
}
