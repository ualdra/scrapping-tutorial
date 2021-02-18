const cheerio = require('cheerio');
const fetch = require('node-fetch');

equipos = [];

init()

async function getSimplePage(webpage){

    const web = await fetch(webpage)
    
    return await web.text();

}

async function imprimirEquipos(){
    console.log(this.equipos)
}

async function init(){
    const web = await getSimplePage("https://www.rfef.es/clasificacion-historica");
    const $ = cheerio.load(web);
    const tabla = $('.table1 > tbody > tr');

    tabla.each((index,element) =>{

        const tds = $(element).find('td');

        const position = $(tds[0]).text();
        const name = $(tds[1]).text();
        const seasons = $(tds[2]).text();
        const wins = $(tds[3]).text();
        const draws = $(tds[4]).text();
        const losses = $(tds[5]).text();
        const goals = $(tds[6]).text();
        const receivedGoals = $(tds[7]).text();
        const points = $(tds[8]).text();

        const clubData = {position: position, name: name, seasons: seasons, wins:wins, draws: draws, losses: losses, goals:goals, receivedGoals: receivedGoals, points:points};

        this.equipos.push(clubData)

    })
    await imprimirEquipos();
}

