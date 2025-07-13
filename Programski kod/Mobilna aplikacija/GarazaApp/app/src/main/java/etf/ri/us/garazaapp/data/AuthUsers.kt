package etf.ri.us.garazaapp.data

import etf.ri.us.garazaapp.model.User

object AuthUsers {
    fun getUsers() : List<User>{
        val users = listOf(
            User(rfid = "4159772003", ime = "Neko", prezime = "Nekic"),
            User(rfid = "8273", ime="none", prezime = "none")
        )

        return users
    }
}