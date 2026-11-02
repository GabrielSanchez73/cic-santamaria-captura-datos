// Lee por la entrada estandar un caso por linea (campos separados por '|') y escribe el JSON
// que produce evento_json.h. Lo usa tests/unit/test_firmware_json.py.
#include <iostream>
#include <sstream>
#include <string>
#include <vector>
#include "../esp32_prueba_ingesta/evento_json.h"

int main() {
  std::string linea;
  while (std::getline(std::cin, linea)) {
    std::vector<std::string> c;
    std::stringstream ss(linea);
    std::string x;
    while (std::getline(ss, x, '|')) c.push_back(x);
    if (c.size() != 13) { std::cout << "ERROR_FORMATO\n"; continue; }
    EventoDatos d;
    d.id_evento = c[0].c_str();
    d.estacion_id = c[1].c_str();
    d.sesion_id = c[2].c_str();
    d.animal_id = c[3] == "-" ? nullptr : c[3].c_str();
    d.animal_id_origen = c[4].c_str();
    d.animal_id_confianza = std::stof(c[5]);
    d.ts_inicio = c[6].c_str();
    d.ts_lectura = c[7].c_str();
    d.secuencia = std::stoi(c[8]);
    d.volumen_l = std::stof(c[9]);
    d.duracion_s = std::stol(c[10]);
    d.estado = c[11].c_str();
    d.origen_dato = c[12].c_str();
    char buf[640];
    int n = construir_evento_json(buf, sizeof buf, d);
    if (n < 0) std::cout << "RECHAZADO\n"; else std::cout << buf << "\n";
  }
  return 0;
}
