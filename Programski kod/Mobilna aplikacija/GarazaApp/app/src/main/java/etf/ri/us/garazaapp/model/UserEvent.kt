package etf.ri.us.garazaapp.model

data class UserEvent(
    val rfid: String,
    val ime: String,
    val prezime: String,
    val viaPin: Boolean,
    val timestamp: Long = System.currentTimeMillis()
)
