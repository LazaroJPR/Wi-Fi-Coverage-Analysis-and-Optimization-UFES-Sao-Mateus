<?php
// Verifica se os parâmetros estão presentes
if (isset($_GET['d']) && isset($_GET['u']) && isset($_GET['p']) && isset($_GET['j']) && isset($_GET['dd']) && isset($_GET['ud']) && isset($_GET['con']) &&  isset($_GET['loc']))>
    // Captura os parâmetros
    $d = $_GET['d'];
    $u = $_GET['u'];
    $p = $_GET['p'];
    $j = $_GET['j'];
    $dd = $_GET['dd'];
    $ud = $_GET['ud'];
    $con = $_GET['con'];
    $loc = $_GET['loc'];

    // Define o nome do arquivo CSV
    $file = 'results.csv';

    // Abre o arquivo para escrita
    $handle = fopen($file, 'a');

    // Escreve os dados no arquivo
    fputcsv($handle, array($d, $u, $p, $j, $dd, $ud, $con, $loc));

    // Fecha o arquivo
    fclose($handle);

    echo "Dados salvos com sucesso!";
} else {
    echo "Parâmetros insuficientes!";
}
?>
