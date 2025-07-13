package etf.ri.us.garazaapp

import android.content.Intent
import android.os.Bundle
import android.widget.Button
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import etf.ri.us.garazaapp.model.UserEvent
import etf.ri.us.garazaapp.ui.theme.GarazaAppTheme
import java.text.DateFormat
import java.util.*

class MainActivity : ComponentActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        // Start MQTT service
        startService(Intent(this, MqttService::class.java))

        // Button: Open
        findViewById<Button>(R.id.btnOpen).setOnClickListener {
            Intent(this, MqttService::class.java).also { intent ->
                intent.action = MqttService.ACTION_PUBLISH
                intent.putExtra(MqttService.EXTRA_TOPIC, "garaza/vrata")
                intent.putExtra(MqttService.EXTRA_MESSAGE, "open")
                startService(intent)
            }
        }

        // Button: Close
        findViewById<Button>(R.id.btnClose).setOnClickListener {
            Intent(this, MqttService::class.java).also { intent ->
                intent.action = MqttService.ACTION_PUBLISH
                intent.putExtra(MqttService.EXTRA_TOPIC, "garaza/vrata")
                intent.putExtra(MqttService.EXTRA_MESSAGE, "close")
                startService(intent)
            }
        }

        findViewById<Button>(R.id.btnAlarmOff).setOnClickListener {
            Intent(this, MqttService::class.java).also { intent ->
                intent.action = MqttService.ACTION_PUBLISH
                intent.putExtra(MqttService.EXTRA_TOPIC, MqttService.TOPIC_OFF)
                intent.putExtra(MqttService.EXTRA_MESSAGE, "alarm_off")
                startService(intent)
            }
        }

        // Button: History
        findViewById<Button>(R.id.btnHistory).setOnClickListener {
            startActivity(Intent(this, HistoryActivity::class.java))
        }

    }
}

class HistoryActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            GarazaAppTheme {
                HistoryScreen(MqttService.history)
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun HistoryScreen(events: List<UserEvent>) {
    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Historija korištenja") }
            )
        }
    ) { paddingValues ->
        LazyColumn(
            modifier = Modifier
                .fillMaxSize()
                .padding(paddingValues)
                .padding(16.dp)
        ) {
            items(events) { ev ->
                Card(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(vertical = 4.dp),
                    elevation = CardDefaults.elevatedCardElevation(defaultElevation = 4.dp)
                ) {
                    Column(modifier = Modifier.padding(12.dp)) {
                        val timeStr = remember(ev.timestamp) {
                            DateFormat.getDateTimeInstance().format(Date(ev.timestamp))
                        }
                        Text(
                            text = timeStr,
                            fontSize = 12.sp,
                            color = Color.Gray
                        )
                        Spacer(Modifier.height(4.dp))
                        Text(
                            text = if (ev.viaPin)
                                "PIN ulaz"
                            else
                                "${ev.ime} ${ev.prezime} (${ev.rfid})",
                            fontSize = 16.sp,
                            fontWeight = FontWeight.SemiBold
                        )
                    }
                }
            }
        }
    }
}
