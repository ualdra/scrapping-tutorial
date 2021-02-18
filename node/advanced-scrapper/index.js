const puppeteer = require('puppeteer');
const cheerio = require('cheerio');

var browser;
var page;

async function getWebPage(webPage, selector){

        this.browser = await puppeteer.launch();
        this.page = await this.browser.newPage();
        await this.page.goto(webPage);
        await this.page.waitForSelector(selector);
        
        return await this.page.content()
        

}


async function init(){
    var pageToBeScrapped = await getWebPage('https://www.ual.es/estudios/grados/presentacion/plandeestudios/4015?idioma=es_ES','#bodyExc > div > div > section.main-container-titulacion.areatitulacion2 > div > div:nth-child(3) > div:nth-child(2) > div > table > tbody > tr:nth-child(5) > td:nth-child(2)')
    //var cuatrimestres = await this.page.$$eval('#bodyExc > div > div > section.main-container-titulacion.areatitulacion2 > div > div')
    const cuatrimestres = await this.page.evaluate(() => Array.from(document.querySelectorAll('#bodyExc > div > div > section.main-container-titulacion.areatitulacion2 > div > div'), e => e.innerHTML));
   

    cuatrimestres.forEach(async (element) => {
        const $ = await cheerio.load(element);
        const rowContent = await $('tr');
        
        rowContent.each((i, cheerioElement)=>{
            var row = $(cheerioElement).find('td')
            var codigo = $(row[0]).text();
            var nombre = $(row[1]).text();
            var creditos = $(row[2]).text();
            var caracter = $(row[3]).text();           
            //console.log()
        })
    });
    await this.browser.close();
    console.log('++++++++The END+++++++++')
}

init()