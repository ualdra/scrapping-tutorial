const cheerio = require('cheerio');
const puppeteer = require('puppeteer');
//const fetch = require('node-fetch')

var grados = [];
init()

async function webAScrappear(web, selector){
    const browser = await puppeteer.launch();
    const page = await browser.newPage();
    await page.goto(web);
    await page.waitForSelector(selector)

    return await page.content()

    
}

async function init(){
    const web = await webAScrappear('https://www.ual.es/estudios/grados', 'body > div > div > div.container.main > div > section > div:nth-child(2) > div:nth-child(17) > div:nth-child(2) > div:nth-child(9) > div > ul > li:nth-child(2) > a > span')
    
    const $ = cheerio.load(web);

    const grados = $('body > div > div > div.container.main > div > section > div:nth-child(2) > div:nth-child(17)')

    $('.sinvinetas > li > a').each((i, elemento) => {
        var nombreG = $(elemento).find('.ng-binding').text()
        var codigoG = $(elemento).attr('href')
        console.log(codigoG)
        var grado = {nombre: nombreG, codigo: codigoG}

    })
    
}


